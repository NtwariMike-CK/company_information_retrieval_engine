"""REST interface + error-tracking evidence: prints real requests/responses (success AND failure paths), then the technical
detail that was kept in the protected `error_logs` table, and what an end user is shown instead.
WARNING: switches the GLOBAL AI config to the test providers and creates a test company - throwaway stack only.
    python tests/rest_interface_samples.py"""
import json, os, time, uuid
import httpx, psycopg

BASE = os.getenv("BASE_URL", "http://localhost:8000")
DB = os.getenv("DATABASE_URL", "postgresql://rag_app:change_me_app@localhost:5432/company_rag")
SA = (os.getenv("SUPERADMIN_EMAIL", "superadmin@example.com"), os.getenv("SUPERADMIN_PASSWORD", "ChangeMe123!"))
c = httpx.Client(base_url=BASE, timeout=60)
run = uuid.uuid4().hex[:6]
rows = []


def call(label, method, path, expect, token=None, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    t = time.perf_counter()
    r = c.request(method, path, headers=h, **kw)
    ms = (time.perf_counter() - t) * 1000
    body = r.text.replace("\n", " ")
    body = body[:110] + ("..." if len(body) > 110 else "")
    ok = r.status_code == expect
    rows.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} | {label:<46} | {method:<6} {path:<34} | expected {expect} got {r.status_code} | {ms:6.1f} ms | {body}")
    return r


print("REST INTERFACE TEST (expected vs actual status code, latency, response body excerpt)\n")
tok = call("login (SuperAdmin)", "POST", "/auth/login", 200, json={"email": SA[0], "password": SA[1]}).json()["access_token"]
c.put("/superadmin/rag-config", headers={"Authorization": f"Bearer {tok}"}, json={"embedding_cfg": {"provider": "fake", "model": "gemini-embedding-2"}, "llm_cfg": {"provider": "fake"}, "retrieval_cfg": {"min_score": 0.25}})
call("login with wrong password", "POST", "/auth/login", 401, json={"email": SA[0], "password": "wrong"})
call("login with malformed email (validation)", "POST", "/auth/login", 422, json={"email": "not-an-email", "password": "x"})
call("protected route without a token", "GET", "/superadmin/companies", 401)
call("protected route with a forged token", "GET", "/superadmin/companies", 401, token="abc.def.ghi")
for i in range(5):
    call(f"brute-force guard: failed attempt {i + 1} of 5", "POST", "/auth/login", 401, json={"email": f"brute-{run}@x.com", "password": "wrong"})
call("brute-force guard: 6th attempt is blocked", "POST", "/auth/login", 429, json={"email": f"brute-{run}@x.com", "password": "wrong"})
call("health check", "GET", "/health", 200)
call("public site content (no login needed)", "GET", "/public/site-content", 200)
adm = call("SuperAdmin creates a company", "POST", "/superadmin/companies", 201, token=tok, json={"company_name": f"Rest-{run}", "admin_name": "Rest Admin", "phone": "+250788000000", "email": f"rest-{run}@x.com", "password": "Password123"}).json()
call("duplicate admin email -> conflict", "POST", "/superadmin/companies", 409, token=tok, json={"company_name": f"Rest2-{run}", "admin_name": "Rest Admin", "phone": "+250788000000", "email": f"rest-{run}@x.com", "password": "Password123"})
at = call("login (Company Admin)", "POST", "/auth/login", 200, json={"email": f"rest-{run}@x.com", "password": "Password123"}).json()["access_token"]
call("Company Admin calls SuperAdmin API (RBAC)", "GET", "/superadmin/companies", 403, token=at)
call("create employee", "POST", "/company/employees", 201, token=at, json={"full_name": "Eve Employee", "email": f"eve-{run}@x.com", "password": "Password123"})
call("create employee with short password (validation)", "POST", "/company/employees", 422, token=at, json={"full_name": "Short Pw", "email": f"sp-{run}@x.com", "password": "123"})
et = call("login (Employee)", "POST", "/auth/login", 200, json={"email": f"eve-{run}@x.com", "password": "Password123"}).json()["access_token"]
call("Employee calls Company Admin API (RBAC)", "GET", "/company/employees", 403, token=et)
call("upload: valid .md + unsupported .exe", "POST", "/company/documents", 202, token=at, files=[("files", ("hr.md", b"# Leave\n\nEmployees get twenty five days of annual leave every year.\n", "text/markdown")), ("files", ("bad.exe", b"MZ", "application/x-msdownload"))])
call("upload a CORRUPT pdf (accepted, fails in the worker)", "POST", "/company/documents", 202, token=at, files=[("files", ("broken.pdf", b"%PDF-1.4 this is not really a pdf", "application/pdf"))])
for _ in range(30):
    docs = c.get("/company/documents", headers={"Authorization": f"Bearer {at}"}).json()
    if docs and all(d["status"] in ("ready", "failed") for d in docs):
        break
    time.sleep(1)
print("\nDOCUMENT STATUS AFTER PROCESSING (what the Company Admin sees):")
for d in docs:
    print(f"  {d['filename']:<12} status={d['status']:<7} user-facing message: {d.get('error_message') or d.get('status_message') or '-'}")
call("chat before the service is started", "POST", "/chat/conversations", 201, token=et)
conv = c.get("/chat/conversations", headers={"Authorization": f"Bearer {et}"}).json()[0]["id"]
call("ask a question before Start -> blocked", "POST", f"/chat/conversations/{conv}/messages", 403, token=et, json={"question": "How many leave days?"})
call("start while a document has FAILED -> refused", "POST", "/company/service/start", 409, token=at)
bad = next(d for d in docs if d["status"] == "failed")
call("delete the failed document", "DELETE", f"/company/documents/{bad['id']}", 200, token=at)
call("start the service", "POST", "/company/service/start", 200, token=at)
r = call("ask a question (RAG answer)", "POST", f"/chat/conversations/{conv}/messages", 200, token=et, json={"question": "How many days of annual leave do employees get?"})
call("ask an empty question (validation)", "POST", f"/chat/conversations/{conv}/messages", 422, token=et, json={"question": ""})
call("open a conversation that does not exist", "GET", f"/chat/conversations/{uuid.uuid4()}", 404, token=et)
call("END service without confirmation (validation)", "POST", "/company/service/end", 422, token=at, json={})

print(f"\nREST RESULT: {sum(rows)} of {len(rows)} requests behaved as specified\n")
print("ERROR TRACKING - technical detail kept server-side (table error_logs, SuperAdmin only), newest first:")
with psycopg.connect(DB) as conn:
    conn.execute("SELECT set_config('app.bypass_rls','on',false)")
    for src, code, msg, det, ts in conn.execute("SELECT source, error_code, message, left(detail,160), created_at FROM error_logs ORDER BY created_at DESC LIMIT 5").fetchall():
        print(f"  {ts:%H:%M:%S} | source={src} | code={code} | message={msg[:70]} | detail={det!r}")
    print("\nAUDIT TRAIL (table audit_logs) - who did what, newest first:")
    for actor, action, tt, ts in conn.execute("SELECT coalesce(u.email,'system'), a.action, a.target_type, a.created_at FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.created_at DESC LIMIT 6").fetchall():
        print(f"  {ts:%H:%M:%S} | {actor:<28} | {action:<28} | {tt}")
raise SystemExit(0 if all(rows) else 1)
