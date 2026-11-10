"""Workbook rows U15, U16, U17 (and I10 evidence). Only 3 Gemini answer calls (U17 asks one question three times).
Env: ADMIN_A_EMAIL/PASSWORD, EMPLOYEE_EMAIL/PASSWORD (employee of company A), ADMIN_B_EMAIL/PASSWORD (admin of ANOTHER company)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from common import ask, client, env, hdr, login

c = client()
adm_a, emp, adm_b = (login(c, env(f"{p}_EMAIL"), env(f"{p}_PASSWORD")) for p in ("ADMIN_A", "EMPLOYEE", "ADMIN_B"))
results = []


def check(row, label, ok, detail):
    results.append(ok)
    print(f"{row} | {'Pass' if ok else 'Fail'} | {label} | {detail}")


r = c.get("/company/employees", headers=hdr(emp))
check("U15", "Employee calls an admin-only endpoint", r.status_code in (401, 403), f"HTTP {r.status_code}")
r = c.get("/company/documents", headers=hdr(emp))
check("U15", "Employee reads the admin document list", r.status_code in (401, 403), f"HTTP {r.status_code}")
r = c.get("/superadmin/companies", headers=hdr(adm_a))
check("U15", "Company admin calls a SuperAdmin endpoint", r.status_code in (401, 403), f"HTTP {r.status_code}")

docs_a = {d["id"] for d in c.get("/company/documents", headers=hdr(adm_a)).json()}
docs_b = {d["id"] for d in c.get("/company/documents", headers=hdr(adm_b)).json()}
check("U16", "Company B admin sees none of company A's documents", not (docs_a & docs_b), f"A has {len(docs_a)}, B has {len(docs_b)}, shared {len(docs_a & docs_b)}")
if docs_a:
    victim = sorted(docs_a)[0]
    r = c.delete(f"/company/documents/{victim}", headers=hdr(adm_b))
    still = victim in {d["id"] for d in c.get("/company/documents", headers=hdr(adm_a)).json()}
    check("U16", "Company B admin tries to delete a document of company A", r.status_code in (403, 404) and still, f"HTTP {r.status_code}, document still present: {still}")

question = f"What is the notice period for resignation? (log check {int(time.time())})"
for _ in range(3):
    res, wall, err = ask(c, emp, question)
    if res is None:
        print("question failed:", err)
norm = " ".join("".join(ch for ch in question.lower() if ch.isalnum() or ch.isspace()).split())
rows = c.get("/company/analytics/questions", headers=hdr(adm_a)).json()
match = [x for x in rows if " ".join("".join(ch for ch in x["question"].lower() if ch.isalnum() or ch.isspace()).split()) == norm]
check("U17", "Same question asked three times", bool(match) and match[0]["times_asked"] == 3,
      f"times_asked={match[0]['times_asked'] if match else 'row not found'}, last_asked={match[0]['last_asked'] if match else '-'}")
print(f"\n{sum(results)} of {len(results)} checks passed")
