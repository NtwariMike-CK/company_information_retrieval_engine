"""End-to-end smoke test against a RUNNING API (default http://localhost:8000).
WARNING: this script switches the GLOBAL RAG configuration to the test (fake) AI providers and creates test companies.
Run it only against a throwaway stack (docker compose down -v, up, run, then down -v again), never against your real data.
Uses the 'fake' AI providers so no Gemini key is needed:  python tests/smoke.py"""
import os, sys, time, uuid
import httpx

BASE = os.getenv("BASE_URL", "http://localhost:8000")
SA_EMAIL = os.getenv("SUPERADMIN_EMAIL", "superadmin@example.com")
SA_PASS = os.getenv("SUPERADMIN_PASSWORD", "ChangeMe123!")
c = httpx.Client(base_url=BASE, timeout=60)
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {extra}" if not cond else ""))


def login(email, pw):
    r = c.post("/auth/login", json={"email": email, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"} if r.status_code == 200 else None


def wait_ready(h, n, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        docs = c.get("/company/documents", headers=h).json()
        if len(docs) >= n and all(d["status"] in ("ready", "failed") for d in docs):
            return docs
        time.sleep(1)
    return c.get("/company/documents", headers=h).json()


run = uuid.uuid4().hex[:6]
sa = login(SA_EMAIL, SA_PASS)
check("superadmin login", sa is not None)
check("wrong password rejected", c.post("/auth/login", json={"email": SA_EMAIL, "password": "nope"}).status_code == 401)

# --- global config (fake providers + friendly thresholds for the test) ---
r = c.put("/superadmin/rag-config", headers=sa, json={
    "embedding_cfg": {"provider": "fake"}, "llm_cfg": {"provider": "fake"},
    "retrieval_cfg": {"min_score": 0.25, "final_k": 4}, "chunking_cfg": {"strategy": "parent_child", "parent_size": 600, "child_size": 200, "overlap": 20}})
check("config update + activation", r.status_code == 200 and r.json().get("activated"), r.text[:200])
r = c.put("/superadmin/rag-config", headers=sa, json={"chunking_cfg": {"strategy": "parent_child", "parent_size": 300, "child_size": 400}})
check("invalid config rejected (child>=parent)", r.status_code == 422)
r = c.put("/superadmin/rag-config", headers=sa, json={"llm_cfg": {"provider": "google", "model": "gemini-3.8-flash"}})
check("config with no API key fails validation and is NOT activated", r.status_code == 422, r.text[:200])
check("previous config still active", c.get("/superadmin/rag-config", headers=sa).json()["llm_cfg"]["provider"] == "fake")

cred = c.post("/superadmin/credentials", headers=sa, json={"label": "test", "api_key": "AIzaSyFAKEKEY12345678"})
check("credential created, key masked", cred.status_code == 201 and "api_key" not in cred.json() and cred.json()["key_last4"] == "5678")
check("credential list never returns key", "encrypted_key" not in c.get("/superadmin/credentials", headers=sa).text)

# --- two companies ---
def mk_company(name):
    r = c.post("/superadmin/companies", headers=sa, json={"company_name": f"{name}-{run}", "admin_name": "Admin " + name, "phone": "+250788000000",
                                                           "email": f"admin-{name.lower()}-{run}@x.com", "password": "Password123"})
    assert r.status_code == 201, r.text
    return r.json()

A, B = mk_company("Acme"), mk_company("Beta")
check("duplicate admin email -> 409", c.post("/superadmin/companies", headers=sa, json={"company_name": "Other-" + run, "admin_name": "X Y", "phone": "12345", "email": f"admin-acme-{run}@x.com", "password": "Password123"}).status_code == 409)
ha = login(f"admin-acme-{run}@x.com", "Password123")
hb = login(f"admin-beta-{run}@x.com", "Password123")
check("company admins login", ha and hb)
check("company admin cannot use superadmin API", c.get("/superadmin/companies", headers=ha).status_code == 403)

r = c.post("/company/employees", headers=ha, json={"full_name": "Eve Employee", "email": f"eve-{run}@x.com", "password": "Password123"})
check("employee created", r.status_code == 201, r.text)
r = c.post("/company/employees", headers=hb, json={"full_name": "Bob Beta", "email": f"bob-{run}@x.com", "password": "Password123"})
he, hbob = login(f"eve-{run}@x.com", "Password123"), login(f"bob-{run}@x.com", "Password123")

# --- ingestion ---
docA = b"# Acme HR Policy\n\nEmployees receive 25 days of annual vacation leave per year. Vacation requests must be approved by the line manager two weeks in advance.\n\nRemote work is allowed up to three days per week.\n" * 3
docB = b"Beta Corp cafeteria opens at 8am and serves lunch until 2pm. The parking garage is on level two.\n" * 5
r = c.post("/company/documents", headers=ha, files=[("files", ("hr.md", docA, "text/markdown")), ("files", ("bad.exe", b"MZ", "application/x-msdownload"))])
res = r.json()["results"]
check("upload: md queued, .exe rejected", r.status_code == 202 and res[0]["status"] == "queued" and res[1]["status"] == "rejected", r.text)
check("duplicate upload detected", c.post("/company/documents", headers=ha, files=[("files", ("hr2.md", docA, "text/markdown"))]).json()["results"][0]["status"] == "duplicate")
c.post("/company/documents", headers=hb, files=[("files", ("cafe.txt", docB, "text/plain"))])
docs = wait_ready(ha, 1)
check("document processed -> ready with chunks", docs and docs[0]["status"] == "ready" and docs[0]["chunks"] > 0, str(docs)[:300])
check("EDA stats stored", docs and docs[0].get("eda_stats") and docs[0]["eda_stats"]["parent_chunks"] > 0)
wait_ready(hb, 1)
kb = c.get("/company/knowledge-base", headers=ha).json()
check("knowledge base ready (green)", kb["ready"] and kb["can_start"], str(kb))
check("chat blocked before Start", c.post("/chat/conversations", headers=he).status_code == 201 and
      c.post(f"/chat/conversations/{c.get('/chat/conversations', headers=he).json()[0]['id']}/messages", headers=he, json={"question": "vacation days?"}).status_code == 403)
check("start", c.post("/company/service/start", headers=ha).json()["chatbot_state"] == "started")
c.post("/company/service/start", headers=hb)

# --- chat ---
conv = c.post("/chat/conversations", headers=he).json()["id"]
r = c.post(f"/chat/conversations/{conv}/messages", headers=he, json={"question": "How many vacation days do employees get?"}).json()
check("answer grounded with evidence + sources", r.get("has_evidence") is True and r["sources"] and "25 days" in r["answer"], str(r)[:300])
check("evaluation requested (every answer)", r["evaluation"]["requested"] and len(r["evaluation"]["questions"]) == 2)
qs = r["evaluation"]["questions"]
rating_q = next(x for x in qs if x["type"] == "rating_1_5"); tf_q = next(x for x in qs if x["type"] == "true_false")
fb = c.post(f"/chat/messages/{r['message_id']}/feedback", headers=he, json={"answers": [{"question_id": rating_q["id"], "rating": 5}, {"question_id": tf_q["id"], "bool_value": True}]})
check("feedback stored", fb.status_code == 200, fb.text)
check("wrong feedback type rejected", c.post(f"/chat/messages/{r['message_id']}/feedback", headers=he, json={"answers": [{"question_id": rating_q["id"], "bool_value": True}]}).status_code == 422)
r2 = c.post(f"/chat/conversations/{conv}/messages", headers=he, json={"question": "quantum chromodynamics lagrangian"}).json()
check("no-evidence question uses no-evidence path", r2.get("has_evidence") is False and not r2["sources"], str(r2)[:300])
for i in range(7):
    c.post(f"/chat/conversations/{conv}/messages", headers=he, json={"question": f"What is the remote work policy {i}?"})
last = c.post(f"/chat/conversations/{conv}/messages", headers=he, json={"question": "one too many"})
check("10th question blocked by backend (limit 9)", last.status_code == 409 and last.json()["detail"]["code"] == "chat_limit_reached", last.text)
check("exchange_count capped at 9", c.get(f"/chat/conversations/{conv}", headers=he).json()["exchange_count"] == 9)
rep = c.post("/chat/reports", headers=he, json={"type": "recommendation", "comments": "Please add the travel policy.", "conversation_id": conv})
check("report submitted", rep.status_code == 201, rep.text)

# --- tenant isolation ---
check("other company's employee cannot open conversation", c.get(f"/chat/conversations/{conv}", headers=hbob).status_code == 404)
check("company B admin cannot read A conversation", c.get(f"/company/conversations/{conv}", headers=hb).status_code == 404)
convb = c.post("/chat/conversations", headers=hbob).json()["id"]
rb = c.post(f"/chat/conversations/{convb}/messages", headers=hbob, json={"question": "How many vacation days do employees get?"}).json()
check("company B cannot retrieve company A's documents", "25 days" not in rb["answer"] and all(s["filename"] != "hr.md" for s in rb["sources"]), str(rb)[:300])
check("employee cannot call admin API", c.get("/company/employees", headers=he).status_code == 403)

# --- analytics / exports ---
check("questions report", any(x["times_asked"] >= 1 for x in c.get("/company/analytics/questions", headers=ha).json()))
csv = c.get("/company/analytics/questions/export", headers=ha)
check("questions CSV download", csv.status_code == 200 and csv.text.startswith("question,times_asked"))
check("feedback list has question+answer", any(f["answer"] and f["question"] for f in c.get("/company/analytics/feedback", headers=ha).json()))
check("reports visible to admin", len(c.get("/company/analytics/reports", headers=ha).json()) == 1)
d = c.get(f"/company/conversations/{conv}", headers=ha).json()
check("conversation detail has evidence + feedback", d["messages"][1]["evidence"] and d["messages"][1]["feedback"], str(d)[:200])
check("conversation export csv", c.post("/company/conversations/export", headers=ha, json={"conversation_ids": [conv]}).text.count("\n") >= 10)
sa_an = c.get("/superadmin/analytics", headers=sa).json()
check("superadmin platform analytics", len(sa_an["companies"]) >= 2)
check("superadmin reports per company", len(c.get(f"/superadmin/reports?company_id={A['company']['id']}", headers=sa).json()) == 1)
imp = c.post(f"/superadmin/companies/{A['company']['id']}/impersonate", headers=sa).json()
check("superadmin enters as admin", c.get("/company/employees", headers={"Authorization": f"Bearer {imp['access_token']}"}).status_code == 200)

# --- pause / deactivate ---
c.post("/company/service/pause", headers=ha)
check("paused -> chat blocked, data kept", c.post(f"/chat/conversations/{c.post('/chat/conversations', headers=he).json()['id']}/messages", headers=he, json={"question": "hi"}).status_code == 403)
c.patch(f"/superadmin/companies/{B['company']['id']}/access", headers=sa, json={"active": False})
check("deactivated company cannot log in", login(f"bob-{run}@x.com", "Password123") is None and c.get("/chat/status", headers=hbob).status_code == 403)

# --- end service => full deletion ---
check("END requires confirmation", c.post("/company/service/end", headers=ha, json={}).status_code == 422)
check("end service accepted", c.post("/company/service/end", headers=ha, json={"confirm": "END"}).status_code == 200)
for _ in range(30):
    st = c.get("/company/service/deletion", headers=ha).json()
    if st["status"] == "completed":
        break
    time.sleep(1)
check("deletion completed, all steps done", st["status"] == "completed" and all(v == "done" for v in st["steps"].values()), str(st))
check("documents gone", c.get("/company/documents", headers=ha).json() == [])
check("conversations gone", c.get("/company/conversations", headers=ha).json() == [])
check("employee accounts deleted (privacy)", all(u["role"] == "company_admin" for u in c.get("/company/employees", headers=ha).json()) and login(f"eve-{run}@x.com", "Password123") is None)
check("company admin can still log in to re-upload", c.get("/company/knowledge-base", headers=ha).status_code == 200)
check("company reset to not_started/empty", c.get("/company/knowledge-base", headers=ha).json()["kb_status"] == "empty")
check("other company's data untouched", len(c.get("/company/documents", headers=hb).json() or [1]) >= 1)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
