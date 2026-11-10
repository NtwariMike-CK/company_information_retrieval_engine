"""Sheets 6_RAG_Eval and 5_Performance (runs 1-30). Reads your questions from the workbook, asks each one in a fresh chat,
and writes the system answer, cited source, Answered/No-data and the timings into a COPY of the workbook.
Cost: one embedding call + one Gemini answer call per question (40 questions = 80 small calls). Nothing else is called.

  python real_run/run_question_set.py Testing_Record_Workbook_1.xlsx            # all questions
  python real_run/run_question_set.py Testing_Record_Workbook_1.xlsx --limit 3  # dry run with 3 questions first
Env: EMPLOYEE_EMAIL, EMPLOYEE_PASSWORD (an employee of the company whose documents you are testing)."""
import argparse, csv, os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
import openpyxl
from common import ask, client, env, login

ap = argparse.ArgumentParser()
ap.add_argument("workbook")
ap.add_argument("--limit", type=int, default=0, help="only the first N questions (use 3 for a dry run)")
ap.add_argument("--out", default="results")
a = ap.parse_args()

wb = openpyxl.load_workbook(a.workbook)
ev, perf = wb["6_RAG_Eval"], wb["5_Performance"]
rows = [r for r in range(6, 46) if ev.cell(r, 3).value and not str(ev.cell(r, 1).value or "").startswith("EXAMPLE")]
if a.limit:
    rows = rows[: a.limit]
if not rows:
    sys.exit("No questions found in sheet 6_RAG_Eval (column C). Fill the questions first.")

c = client()
token = login(c, env("EMPLOYEE_EMAIL"), env("EMPLOYEE_PASSWORD"))
os.makedirs(a.out, exist_ok=True)
log = []
for n, r in enumerate(rows, 1):
    qid, lang, question = ev.cell(r, 1).value, ev.cell(r, 2).value, str(ev.cell(r, 3).value)
    expected_src = str(ev.cell(r, 6).value or "")
    res, wall, error = ask(c, token, question)
    if res is None:
        print(f"{qid}: ERROR {error}")
        ev.cell(r, 15).value = f"ERROR: {error}"
        log.append({"q_id": qid, "error": error, "wall_s": round(wall, 2)})
        continue
    sources = sorted({s["filename"] for s in res["sources"]})
    t = res.get("timing", {})
    status = "Answered" if res["has_evidence"] else "No-data"
    ev.cell(r, 7).value = res["answer"]
    ev.cell(r, 8).value = "; ".join(sources)
    ev.cell(r, 9).value = status
    src_ok = (expected_src in sources) if expected_src and expected_src.lower() not in ("none", "n/a", "-") else None
    ev.cell(r, 15).value = {True: "auto: expected source cited", False: "auto: expected source NOT cited", None: ""}[src_ok]
    if n <= 30:  # sheet 5 has 30 timing rows (rows 6-35)
        pr = 5 + n
        perf.cell(pr, 2).value, perf.cell(pr, 3).value = lang, "Answerable" if ev.cell(r, 4).value == "Yes" else "Not in documents"
        perf.cell(pr, 4).value, perf.cell(pr, 5).value, perf.cell(pr, 6).value = t.get("total_s"), t.get("retrieval_s"), t.get("generation_s")
        perf.cell(pr, 7).value = status
    log.append({"q_id": qid, "lang": lang, "status": status, "expected_source": expected_src, "sources": "; ".join(sources),
                "source_ok": src_ok, "wall_s": round(wall, 2), **t, "answer": res["answer"]})
    print(f"{qid}: {status:<8} total {t.get('total_s')} s (retrieval {t.get('retrieval_s')}, generation {t.get('generation_s')})  sources: {', '.join(sources) or '-'}")

out_wb = os.path.join(a.out, "Testing_Record_Workbook_filled.xlsx")
wb.save(out_wb)
with open(os.path.join(a.out, "question_set_results.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=sorted({k for row in log for k in row}, key=lambda k: (k != "q_id", k)))
    w.writeheader(); w.writerows(log)
print(f"\nSaved {out_wb} and question_set_results.csv. Now mark column J (Correct / Partly / Wrong) yourself by reading each answer.")
