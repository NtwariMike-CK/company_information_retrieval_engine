"""Prints a step-by-step TRACE of one document and one question travelling through the whole system, with database
evidence at every step (client -> API -> worker -> PostgreSQL/pgvector -> retrieval -> LLM -> storage -> analytics -> deletion).
Uses the test AI providers. WARNING: changes the global AI configuration; use a throwaway stack.   python tests/data_flow_trace.py"""
import os, sys, time, uuid
import httpx, psycopg

BASE = os.getenv("BASE_URL", "http://localhost:8000")
DB = os.getenv("DATABASE_URL", "postgresql://rag_app:change_me_app@localhost:5432/company_rag")
SA = (os.getenv("SUPERADMIN_EMAIL", "superadmin@example.com"), os.getenv("SUPERADMIN_PASSWORD", "ChangeMe123!"))
c = httpx.Client(base_url=BASE, timeout=60)
run = uuid.uuid4().hex[:6]
n = 0


def step(title):
    global n
    n += 1
    print(f"\n[{n:02d}] {title}")


def db(sql, *a):
    with psycopg.connect(DB) as conn:
        conn.execute("SELECT set_config('app.bypass_rls','on',false)")
        cur = conn.execute(sql, a or None)
        return cur.fetchall() if cur.description else None


def tok(r):
    return {"Authorization": "Bearer " + r.json()["access_token"]}


step("SuperAdmin signs in and activates the (test) AI configuration")
sa = tok(c.post("/auth/login", json={"email": SA[0], "password": SA[1]}))
r = c.put("/superadmin/rag-config", headers=sa, json={"embedding_cfg": {"provider": "fake", "model": "gemini-embedding-2"}, "llm_cfg": {"provider": "fake"}, "retrieval_cfg": {"min_score": 0.25, "final_k": 4}, "chunking_cfg": {"strategy": "parent_child", "parent_size": 600, "child_size": 200, "overlap": 20}})
print(f"  PUT /superadmin/rag-config -> HTTP {r.status_code}; activated={r.json().get('activated')}; live validation={r.json()['validation'].get('ok')}")
print("  DB rag_config_versions:", db("select version, status from rag_config_versions order by version desc limit 2"))

step("SuperAdmin registers a company (company + admin created in one transaction)")
r = c.post("/superadmin/companies", headers=sa, json={"company_name": f"Trace Co {run}", "admin_name": "Trace Admin", "phone": "12345678", "email": f"trace-{run}@x.com", "password": "Password123"})
cid = r.json()["company"]["id"]
print(f"  POST /superadmin/companies -> HTTP {r.status_code}; company_id={cid}")
print("  DB companies:", db("select name, access_status, chatbot_state, kb_status from companies where id=%s", cid))
print("  DB users (password stored as Argon2 hash):", [(x[0], x[1], x[2][:22] + "...") for x in db("select email, role, password_hash from users where company_id=%s", cid)])

step("Company admin signs in, adds an employee and uploads a document")
ha = tok(c.post("/auth/login", json={"email": f"trace-{run}@x.com", "password": "Password123"}))
c.post("/company/employees", headers=ha, json={"full_name": "Trace Employee", "email": f"emp-{run}@x.com", "password": "Password123"})
doc = ("# Leave policy\n\nEmployees are entitled to twenty-five days of paid annual leave per year.\n\n# Remote work\n\nStaff may work remotely three days per week.\n\n"
       "# Igihe cy'igeragezwa\n\nIgihe cy'igeragezwa ni amezi atatu.\n").encode()
r = c.post("/company/documents", headers=ha, files=[("files", ("handbook.md", doc, "text/markdown"))])
print(f"  POST /company/documents -> HTTP {r.status_code}; result={r.json()['results'][0]['status']}")
seen = []
t0 = time.time()
while time.time() - t0 < 60:
    d = c.get("/company/documents", headers=ha).json()[0]
    key = (d["stage"], d["status"])
    if key not in seen:
        seen.append(key); print(f"  worker progress: stage={d['stage']:8s} status={d['status']:10s} progress={d['progress_pct']}%")
    if d["status"] in ("ready", "failed"):
        break
    time.sleep(0.3)
print("  DB documents:", db("select filename, status, embedding_model, size_bytes from documents where company_id=%s", cid))
print("  DB processing_jobs:", db("select stage, status, progress_pct from processing_jobs where company_id=%s", cid))
print("  DB parent_chunks / chunks:", db("select (select count(*) from parent_chunks where company_id=%s), (select count(*) from chunks where company_id=%s)", cid, cid))
print("  DB embedding dimension of stored vectors:", db("select distinct vector_dims(embedding) from chunks where company_id=%s", cid))
print("  DB chunk languages (metadata):", db("select metadata->>'lang', count(*) from chunks where company_id=%s group by 1 order by 1", cid))
print("  DB sample chunk:", repr(db("select content from chunks where company_id=%s order by chunk_index limit 1", cid)[0][0][:90]))
print("  EDA statistics:", {k: v for k, v in (d.get("eda_stats") or {}).items() if k in ("pages", "words", "chunks", "parent_chunks", "paragraphs_by_language")})

step("Company admin starts the service; employee asks questions")
print("  POST /company/service/start ->", c.post("/company/service/start", headers=ha).json())
he = tok(c.post("/auth/login", json={"email": f"emp-{run}@x.com", "password": "Password123"}))
conv = c.post("/chat/conversations", headers=he).json()["id"]
for q in ("How many days of annual leave do employees get?", "Igihe cy'igeragezwa kimara igihe kingana iki?", "Who won the football match yesterday?"):
    a = c.post(f"/chat/conversations/{conv}/messages", headers=he, json={"question": q}).json()
    print(f"  Q: {q}\n     lang={a['language']} has_evidence={a['has_evidence']} sources={[s['filename'] for s in a['sources']]} remaining={a['remaining_exchanges']}\n     A: {a['answer'][:110]}")
    last = a
print("  DB messages stored:", db("select exchange_no, role, left(content, 38), has_evidence, language from messages where conversation_id=%s order by exchange_no, role desc", conv))
print("  DB retrieval_logs for the last answer (evidence trail):", db("select rank, round(dense_score::numeric, 3), round(sparse_score::numeric, 3), round(fused_score::numeric, 4), used_in_prompt from retrieval_logs where message_id=%s order by rank limit 3", last["message_id"]))
print("  DB conversation counter:", db("select exchange_count from conversations where id=%s", conv))

step("Employee rates the answer and reports an issue; admin sees both in analytics")
q = last["evaluation"]["questions"]
c.post(f"/chat/messages/{last['message_id']}/feedback", headers=he, json={"answers": [{"question_id": next(x["id"] for x in q if x["type"] == "rating_1_5"), "rating": 5}, {"question_id": next(x["id"] for x in q if x["type"] == "true_false"), "bool_value": True}]})
c.post("/chat/reports", headers=he, json={"type": "recommendation", "comments": "Please add the travel policy.", "conversation_id": conv})
print("  DB feedback rows:", db("select rating, bool_value from feedback where company_id=%s order by created_at", cid))
print("  DB reports:", db("select type, status from reports where company_id=%s", cid))
ov = c.get("/company/analytics/overview", headers=ha).json()
print(f"  GET /company/analytics/overview -> questions={ov['questions']} no_evidence={ov['no_evidence']} avg_rating={ov['avg_rating']} conversations={ov['conversations']}")
print("  GET /company/analytics/questions ->", [(x['question'][:30], x['times_asked'], x['information_present']) for x in c.get('/company/analytics/questions', headers=ha).json()][:3])

step("Admin ends the service: tracked deletion; nothing is left behind")
c.post("/company/service/end", headers=ha, json={"confirm": "END"})
for _ in range(40):
    s = c.get("/company/service/deletion", headers=ha).json()
    if s["status"] == "completed":
        break
    time.sleep(0.5)
print("  deletion job:", s["status"], s["steps"])
print("  DB rows left for the company (documents, chunks, conversations, messages, employees):", db("select (select count(*) from documents where company_id=%s), (select count(*) from chunks where company_id=%s), (select count(*) from conversations where company_id=%s), (select count(*) from messages where company_id=%s), (select count(*) from users where company_id=%s and role='employee')", cid, cid, cid, cid, cid))
print("  DB anonymised_feedback keeps only:", db("select kind, evaluation_text, rating, bool_value, report_type from anonymised_feedback order by id desc limit 3"))
print("\nTRACE COMPLETE")
