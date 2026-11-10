"""End-to-end test of v1.1 features against a RUNNING API (fake AI providers, no Gemini key needed):
WARNING: this script switches the GLOBAL RAG configuration to the test (fake) AI providers and creates test companies.
Run it only against a throwaway stack (docker compose down -v, up, run, then down -v again), never against your real data.
public site, applicant registration, request review workflow, onboarding + terms, company creation,
CMS (versioned terms, form fields, languages), Kinyarwanda/English retrieval, anonymisation, data export, model switch.
Run:  python tests/smoke_v11.py"""
import io, os, sys, time, uuid, zipfile
import httpx
import psycopg

BASE = os.getenv("BASE_URL", "http://localhost:8000")
DB = os.getenv("DATABASE_URL", "postgresql://rag_app:change_me_app@localhost:5432/company_rag")
c = httpx.Client(base_url=BASE, timeout=60)
ok = fail = 0
run = uuid.uuid4().hex[:6]


def check(name, cond, extra=""):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {extra}" if not cond else ""))


def auth(r):
    return {"Authorization": f"Bearer {r.json()['access_token']}"} if r.status_code in (200, 201) else None


def db(sql, *args):
    with psycopg.connect(DB) as conn:
        conn.execute("SELECT set_config('app.bypass_rls','on',false)")     # tests may read every tenant's rows
        cur = conn.execute(sql, args or None)
        return cur.fetchall() if cur.description else None


def wait_docs(h, n, timeout=90):
    t = time.time()
    while time.time() - t < timeout:
        docs = c.get("/company/documents", headers=h).json()
        if len(docs) >= n and all(d["status"] in ("ready", "failed") for d in docs):
            return docs
        time.sleep(1)
    return c.get("/company/documents", headers=h).json()


sa = auth(c.post("/auth/login", json={"email": "superadmin@example.com", "password": "ChangeMe123!"}))
check("superadmin login", sa is not None)
c.put("/superadmin/rag-config", headers=sa, json={"embedding_cfg": {"provider": "fake", "model": "gemini-embedding-2"}, "llm_cfg": {"provider": "fake"},
      "retrieval_cfg": {"min_score": 0.25, "final_k": 4}, "chunking_cfg": {"strategy": "parent_child", "parent_size": 600, "child_size": 200, "overlap": 20}})

# ---------- public marketing + legal ----------
site = c.get("/public/site-content").json()
check("public landing sections come from the database", len(site) >= 7 and site[0]["key"] == "hero" and site[0]["content"]["title"])
legal = c.get("/public/legal").json()
check("public terms: 3 steps, terms requires acceptance", len(legal) == 3 and [s["key"] for s in legal] == ["data_guidelines", "privacy_summary", "terms"] and legal[2]["requires_acceptance"])
check("public languages: English + Kinyarwanda", {l["code"] for l in c.get("/public/languages").json()} >= {"en", "rw"})

# ---------- applicant registration ----------
email = f"applicant-{run}@x.com"
r = c.post("/public/register", json={"full_name": "Aline Uwase", "phone": "+250788123456", "email": email, "password": "Password123"})
ap = auth(r)
check("applicant registers", r.status_code == 201 and ap is not None and r.json()["user"]["role"] == "applicant", r.text[:200])
check("duplicate registration -> 409", c.post("/public/register", json={"full_name": "Aline Uwase", "phone": "+250788123456", "email": email, "password": "Password123"}).status_code == 409)
check("weak password rejected", c.post("/public/register", json={"full_name": "X Y", "phone": "12345", "email": f"w-{run}@x.com", "password": "short"}).status_code == 422)
check("applicant cannot call admin / superadmin / chat APIs",
      all(c.get(p, headers=ap).status_code == 403 and c.get(p, headers=ap).json()["detail"]["code"] == "forbidden" for p in ("/company/employees", "/superadmin/companies", "/chat/status")))
check("applicant can log in (no company yet)", auth(c.post("/auth/login", json={"email": email, "password": "Password123"})) is not None)
check("applicant cannot see other roles' content API", c.get("/superadmin/applications", headers=ap).status_code == 403)

form = c.get("/apply/form", headers=ap).json()
check("form fields come from the database", {"company_name", "services", "employee_count", "document_languages"} <= {f["key"] for f in form})
good = {"company_name": f"Umurage Coffee {run}", "industry": "Agriculture", "services": "We export specialty coffee and train cooperatives.",
        "country": "Rwanda", "city": "Huye", "employee_count": 40, "document_languages": ["English", "Kinyarwanda"], "intended_use": "HR policies and export procedures."}
r = c.post("/apply/applications", headers=ap, json={"answers": {"company_name": "X"}})
check("incomplete request rejected with field errors", r.status_code == 422 and r.json()["detail"]["code"] == "validation_failed" and "fields" in r.json()["detail"], r.text[:200])
r = c.post("/apply/applications", headers=ap, json={"answers": {**good, "industry": "Not a real industry"}})
check("invalid select value rejected", r.status_code == 422)
r = c.post("/apply/applications", headers=ap, json={"answers": good})
app1 = r.json().get("id")
check("request submitted -> pending", r.status_code == 201 and r.json()["status"] == "pending" and r.json()["messages"][0]["kind"] == "submission", r.text[:200])
check("only ONE open request at a time", c.post("/apply/applications", headers=ap, json={"answers": good}).status_code == 409)
check("onboarding locked until approved", c.get("/apply/onboarding", headers=ap).status_code == 403)
check("emails queued for applicant and superadmin", db("select count(*) from email_outbox where application_id=%s", app1)[0][0] >= 2)

# ---------- review workflow ----------
lst = c.get("/superadmin/applications?status=pending", headers=sa).json()
check("superadmin sees the pending request", any(a["id"] == app1 for a in lst))
check("summary counts", c.get("/superadmin/applications/summary", headers=sa).json().get("pending", 0) >= 1)
d = c.get(f"/superadmin/applications/{app1}", headers=sa).json()
check("review detail has applicant, answers and form definition", d["applicant"]["email"] == email and d["answers"]["city"] == "Huye" and len(d["fields"]) >= 8)
check("request-info needs a comment", c.post(f"/superadmin/applications/{app1}/decision", headers=sa, json={"action": "request_info", "comment": ""}).status_code == 422)
r = c.post(f"/superadmin/applications/{app1}/decision", headers=sa, json={"action": "request_info", "comment": "Please share your company registration number."})
check("request more information -> needs_info", r.status_code == 200 and r.json()["status"] == "needs_info")
st = c.get("/apply/state", headers=ap).json()
check("applicant sees the reviewer's comment", st["current"]["status"] == "needs_info" and "registration number" in st["current"]["messages"][-1]["body"] and not st["can_submit"])
r = c.post(f"/apply/applications/{app1}/respond", headers=ap, json={"message": "Registration number: RW-123456.", "answers": {"additional_info": "Reg: RW-123456"}})
check("applicant responds -> back to pending, answers updated", r.status_code == 200 and r.json()["status"] == "pending" and r.json()["answers"]["additional_info"] == "Reg: RW-123456")
check("cannot respond when nothing was asked", c.post(f"/apply/applications/{app1}/respond", headers=ap, json={"message": "hello again"}).status_code == 409)
check("reject needs a comment", c.post(f"/superadmin/applications/{app1}/decision", headers=sa, json={"action": "reject", "comment": ""}).status_code == 422)
r = c.post(f"/superadmin/applications/{app1}/decision", headers=sa, json={"action": "reject", "comment": "Please describe the intended use in more detail."})
check("reject with comment", r.status_code == 200 and r.json()["status"] == "rejected")
st = c.get("/apply/state", headers=ap).json()
check("after rejection the applicant can submit again", st["can_submit"] and st["current"]["decision_comment"].startswith("Please describe"))
check("cannot approve an already rejected request", c.post(f"/superadmin/applications/{app1}/decision", headers=sa, json={"action": "approve"}).status_code == 409)
r = c.post("/apply/applications", headers=ap, json={"answers": {**good, "intended_use": "HR policies, export procedures and staff training manuals."}, "resubmission_of": app1})
app2 = r.json().get("id")
check("resubmission accepted -> pending", r.status_code == 201 and app2 != app1, r.text[:200])

# company-name clash blocks approval
c.post("/superadmin/companies", headers=sa, json={"company_name": f"Clash Ltd {run}", "admin_name": "Clash Admin", "phone": "12345678", "email": f"clash-{run}@x.com", "password": "Password123"})
b = auth(c.post("/public/register", json={"full_name": "Bob Clash", "phone": "12345678", "email": f"bob-{run}@x.com", "password": "Password123"}))
rb = c.post("/apply/applications", headers=b, json={"answers": {**good, "company_name": f"clash ltd {run}"}})
check("approval blocked when the company name already exists", c.post(f"/superadmin/applications/{rb.json()['id']}/decision", headers=sa, json={"action": "approve"}).status_code == 409)

r = c.post(f"/superadmin/applications/{app2}/decision", headers=sa, json={"action": "approve", "comment": "Welcome aboard!"})
check("approve -> approved (company not created yet)", r.status_code == 200 and r.json()["status"] == "approved")
check("company NOT created before terms are accepted", db("select count(*) from companies where name=%s", good["company_name"])[0][0] == 0)

# ---------- onboarding walkthrough ----------
steps = c.get("/apply/onboarding", headers=ap).json()
check("walkthrough: 3 pages from the database", [s["key"] for s in steps] == ["data_guidelines", "privacy_summary", "terms"] and "Kinyarwanda" in steps[0]["body_markdown"])
accept_all = [{"step_id": s["step_id"], "version_id": s["version_id"]} for s in steps]
check("cannot finish without accepting the terms", c.post("/apply/onboarding/complete", headers=ap, json={"accepted": accept_all[:2]}).status_code == 422)
check("applicant still not an admin", c.get("/company/employees", headers=ap).status_code == 403)
r = c.post("/apply/onboarding/complete", headers=ap, json={"accepted": accept_all})
check("accepting creates the company and makes the applicant its admin", r.status_code == 200 and r.json()["next"] == "/admin" and r.json()["company"]["name"] == good["company_name"], r.text[:200])
me = c.get("/auth/me", headers=ap).json()
check("same token now acts as company admin", me["role"] == "company_admin" and me["company_name"] == good["company_name"] and c.get("/company/employees", headers=ap).status_code == 200)
check("applicant cannot onboard twice", c.post("/apply/onboarding/complete", headers=ap, json={"accepted": accept_all}).status_code in (403, 409))
req = c.get("/company/request", headers=ap).json()
check("admin can review their request and accepted terms (sidebar page)", req["application"]["status"] == "onboarded" and len(req["accepted_terms"]) == 3 and any(m["kind"] == "approval" for m in req["application"]["messages"]))
check("superadmin sees the company", any(x["name"] == good["company_name"] for x in c.get("/superadmin/companies", headers=sa).json()))
check("acceptance audit trail stored (version + time + ip)", db("select count(*) from terms_acceptances where user_id=(select id from users where email=%s) and ip_address is not null", email)[0][0] == 3)
check("manually created admins still have no request", c.get("/company/request", headers=auth(c.post("/auth/login", json={"email": f"clash-{run}@x.com", "password": "Password123"}))).json()["application"] is None)

# ---------- CMS: versioned terms, form fields, site content, languages ----------
stp = c.get("/superadmin/onboarding-steps", headers=sa).json()
terms = next(s for s in stp if s["key"] == "terms")
v0 = terms["version"]
check("current terms version has this run's acceptances recorded", db("select count(*) from terms_acceptances where step_version_id=%s", terms["current_version_id"])[0][0] >= 1)
r = c.put(f"/superadmin/onboarding-steps/{terms['id']}", headers=sa, json={"body_markdown": terms["body_markdown"] + "\n\n**13. Added clause.** Test."})
check("editing terms publishes a NEW version", r.status_code == 200 and r.json()["version"] == v0 + 1 and r.json()["versions"] == v0 + 1, r.text[:200])
vs = c.get(f"/superadmin/onboarding-steps/{terms['id']}/versions", headers=sa).json()
check("old version kept with its acceptances", len(vs) == v0 + 1 and vs[0]["version"] == v0 + 1 and vs[1]["version"] == v0 and vs[1]["acceptances"] >= 1, str(vs)[:200])
c2 = auth(c.post("/public/register", json={"full_name": "Carl New", "phone": "12345678", "email": f"carl-{run}@x.com", "password": "Password123"}))
a3 = c.post("/apply/applications", headers=c2, json={"answers": {**good, "company_name": f"Carl Co {run}"}}).json()["id"]
c.post(f"/superadmin/applications/{a3}/decision", headers=sa, json={"action": "approve"})
old_ver = [{"step_id": s["step_id"], "version_id": s["version_id"]} for s in steps]     # the OLD (v1) version ids
check("accepting an outdated terms version is refused", c.post("/apply/onboarding/complete", headers=c2, json={"accepted": old_ver}).status_code == 422)
new_steps = c.get("/apply/onboarding", headers=c2).json()
check("new applicant sees the latest terms", next(s for s in new_steps if s["key"] == "terms")["version"] == v0 + 1)
check("...and can onboard with them", c.post("/apply/onboarding/complete", headers=c2, json={"accepted": [{"step_id": s["step_id"], "version_id": s["version_id"]} for s in new_steps]}).status_code == 200)

hero = next(s for s in site if s["key"] == "hero")
r = c.put("/superadmin/site-content/hero", headers=sa, json={"content": {**hero["content"], "title": f"New headline {run}"}})
check("landing content editable and served publicly", r.status_code == 200 and next(s for s in c.get("/public/site-content").json() if s["key"] == "hero")["content"]["title"] == f"New headline {run}")
fld = c.post("/superadmin/application-fields", headers=sa, json={"key": f"registration_{run[:4]}", "label": "Registration number", "type": "text", "required": False, "position": 11})
check("form field added in the database", fld.status_code == 201)
dave = auth(c.post("/public/register", json={"full_name": "Dave Fresh", "phone": "12345678", "email": f"dave-{run}@x.com", "password": "Password123"}))
check("new field appears in a fresh applicant's form", any(f["key"] == f"registration_{run[:4]}" for f in c.get("/apply/form", headers=dave).json()))
check("system field cannot be deleted", c.delete(f"/superadmin/application-fields/{next(f for f in c.get('/superadmin/application-fields', headers=sa).json() if f['key'] == 'company_name')['id']}", headers=sa).status_code == 409)
check("custom field can be deleted", c.delete(f"/superadmin/application-fields/{fld.json()['id']}", headers=sa).status_code == 200)
sw = c.post("/superadmin/languages", headers=sa, json={"code": "sw", "name": "Swahili", "native_name": "Kiswahili", "stopwords": ["na", "ya", "wa", "kwa", "ni"], "is_enabled": False})
check("a new language is just data (Swahili added)", sw.status_code == 201)
check("English cannot be deleted", c.delete("/superadmin/languages/en", headers=sa).status_code == 409)
c.delete("/superadmin/languages/sw", headers=sa)

# ---------- Kinyarwanda + English retrieval in the new company ----------
ha = ap
emp = c.post("/company/employees", headers=ha, json={"full_name": "Eric Mugisha", "email": f"eric-{run}@x.com", "password": "Password123"})
he = auth(c.post("/auth/login", json={"email": f"eric-{run}@x.com", "password": "Password123"}))
doc = ("# Politiki y'ikiruhuko\n\nAbakozi bemerewe iminsi makumyabiri n'itanu y'ikiruhuko buri mwaka. Umukozi asaba ikiruhuko mbere y'ibyumweru bibiri.\n\n"
       "# Remote work\n\nStaff may work remotely up to three days per week with manager approval.\n").encode()
r = c.post("/company/documents", headers=ha, files=[("files", ("policies.md", doc, "text/markdown"))])
docs = wait_docs(ha, 1)
check("bilingual document processed", docs and docs[0]["status"] == "ready", str(docs)[:300])
langs = (docs[0].get("eda_stats") or {}).get("paragraphs_by_language", {})
check("EDA reports both languages", langs.get("rw", 0) >= 1 and langs.get("en", 0) >= 1, str(langs))
check("embedding model recorded on the document", db("select embedding_model from documents where company_id=%s", me["company_id"])[0][0] == "gemini-embedding-2")
check("start", c.post("/company/service/start", headers=ha).status_code == 200)
conv = c.post("/chat/conversations", headers=he).json()["id"]
q_rw = c.post(f"/chat/conversations/{conv}/messages", headers=he, json={"question": "Abakozi bemerewe iminsi ingahe y'ikiruhuko buri mwaka?"}).json()
check("Kinyarwanda question: language detected, evidence found, answered in Kinyarwanda",
      q_rw.get("language") == "rw" and q_rw.get("has_evidence") is True and q_rw["answer"].startswith("Ukurikije"), str(q_rw)[:300])
q_en = c.post(f"/chat/conversations/{conv}/messages", headers=he, json={"question": "How many days of leave are employees entitled to each year?"}).json()
check("English question finds the KINYARWANDA document (cross-language)", q_en.get("language") == "en" and q_en.get("has_evidence") is True and any(s["filename"] == "policies.md" for s in q_en["sources"]), str(q_en)[:300])
q_none = c.post(f"/chat/conversations/{conv}/messages", headers=he, json={"question": "Ni iki gitera imvura n'umuyaga mu kirere cy'isi?"}).json()
check("no-evidence answer comes back in Kinyarwanda", q_none.get("has_evidence") is False and q_none["answer"].startswith("Sinabashije"), str(q_none)[:300])
fb_q = q_rw["evaluation"]["questions"]
c.post(f"/chat/messages/{q_rw['message_id']}/feedback", headers=he, json={"answers": [{"question_id": next(x["id"] for x in fb_q if x["type"] == "rating_1_5"), "rating": 4}, {"question_id": next(x["id"] for x in fb_q if x["type"] == "true_false"), "bool_value": True}]})
c.post("/chat/reports", headers=he, json={"type": "recommendation", "comments": "Add the travel policy please (secret company text).", "conversation_id": conv})

check("language self-check (embedding passes for English<->Kinyarwanda)",
      (lambda r: r.status_code == 200 and r.json()["languages"][0]["code"] == "rw" and r.json()["languages"][0]["embedding"]["ok"])(c.post("/superadmin/languages/check", headers=sa)), c.post("/superadmin/languages/check", headers=sa).text[:300])

# ---------- switching embedding model re-processes documents ----------
r = c.put("/superadmin/rag-config", headers=sa, json={"embedding_cfg": {"provider": "fake", "model": f"fake-embed-{run}"}})
check("changing the embedding model re-queues existing documents", r.status_code == 200 and r.json()["reprocessing_documents"] >= 1, r.text[:200])
docs = wait_docs(ha, 1)
check("documents re-embedded with the new model", docs[0]["status"] == "ready" and db("select embedding_model from documents where company_id=%s", me["company_id"])[0][0] == f"fake-embed-{run}")
q2 = c.post(f"/chat/conversations/{c.post('/chat/conversations', headers=he).json()['id']}/messages", headers=he, json={"question": "How many days of leave are employees entitled to each year?"}).json()
check("chat still works after the model switch", q2.get("has_evidence") is True, str(q2)[:200])

# regression test for a bug found by load testing: slow requests must not hold pooled DB connections (pool size is 10)
from concurrent.futures import ThreadPoolExecutor


def _ask(_):
    cl = httpx.Client(base_url=BASE, timeout=60)
    cv = cl.post("/chat/conversations", headers=he).json()["id"]
    return cl.post(f"/chat/conversations/{cv}/messages", headers=he, json={"question": "How many days of leave are employees entitled to each year?"}).status_code


with ThreadPoolExecutor(12) as pool_:
    codes = list(pool_.map(_ask, range(12)))
check("12 simultaneous chat requests all succeed (no connection-pool starvation)", all(x == 200 for x in codes), str(codes))

# ---------- export + deletion + anonymisation ----------
z = c.get("/company/export", headers=ha)
names = zipfile.ZipFile(io.BytesIO(z.content)).namelist() if z.status_code == 200 else []
check("data export ZIP: documents + CSV files", z.status_code == 200 and any(n.startswith("documents/") for n in names) and {"conversations.csv", "questions.csv", "feedback.csv", "reports.csv"} <= set(names), str(names))
before = db("select count(*) from anonymised_feedback")[0][0]
check("end service accepted", c.post("/company/service/end", headers=ha, json={"confirm": "END"}).status_code == 200)
for _ in range(40):
    s = c.get("/company/service/deletion", headers=ha).json()
    if s["status"] == "completed":
        break
    time.sleep(1)
check("deletion completed incl. anonymise step", s["status"] == "completed" and s["steps"].get("anonymize") == "done" and all(v == "done" for v in s["steps"].values()), str(s))
rows = db("select kind, evaluation_text, rating, bool_value, report_type from anonymised_feedback order by id desc limit 3")
check("anonymised records kept: scores + report category only", db("select count(*) from anonymised_feedback")[0][0] >= before + 3 and any(r[0] == "report" and r[4] == "recommendation" for r in rows), str(rows))
check("anonymised table has no company/user/text columns", {r[0] for r in db("select column_name from information_schema.columns where table_name='anonymised_feedback'")} == {"id", "recorded_month", "kind", "evaluation_text", "rating", "bool_value", "report_type", "created_at"})
check("report comment text was deleted with the company", db("select count(*) from reports where comments like %s", "%secret company text%")[0][0] == 0)
check("admin account (ex-applicant) survives to re-onboard documents", c.get("/company/knowledge-base", headers=ha).json()["kb_status"] == "empty")
check("employee account deleted", auth(c.post("/auth/login", json={"email": f"eric-{run}@x.com", "password": "Password123"})) is None)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
