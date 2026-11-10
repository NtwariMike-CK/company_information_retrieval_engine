# Real test run on your MacBook (low token use)

Everything here uses your real app and your real Gemini key, but the whole run is about **110-130 Gemini answer calls** (plus the
same number of tiny embedding calls). The unit tests need **zero** calls. Check your usage in Google AI Studio before and after.

## 0. Do NOT run these on your real stack
`smoke.py`, `smoke_v11.py`, `smoke_eval.py`, `benchmark.py`, `collect_eval_results.py`, `rest_interface_samples.py`,
`data_flow_trace.py`, `e2e_browser.py`, `run_all_tests.sh`. They switch the whole app to fake AI providers and create test companies.
They are only for a throwaway copy of the app.

## 1. One-time setup
```bash
docker compose up -d --build        # rebuild so the backend now reports retrieval/generation timing
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest pytest-cov httpx openpyxl
```
Put the real documents you will be tested on in one test company (Super Admin creates it, or use your demo company) and start the service.
Use the same documents the supervisor/research team expects (e.g. HR_Policy.pdf). Create one employee in that company.
For the cross-company checks you also need a second company with a different document and its admin.

## 2. Accounts (once per terminal)
```bash
export BASE_URL=http://localhost:8000
export EMPLOYEE_EMAIL=...   EMPLOYEE_PASSWORD=...          # employee of company A
export ADMIN_EMAIL=...      ADMIN_PASSWORD=...             # admin of company A
export ADMIN_A_EMAIL=$ADMIN_EMAIL ADMIN_A_PASSWORD=$ADMIN_PASSWORD
export ADMIN_B_EMAIL=...    ADMIN_B_PASSWORD=...           # admin of company B
```

## 3. Runs, in this order

| # | Workbook sheet | Command | Gemini calls | What to copy into the workbook |
|---|---|---|---|---|
| 1 | 2_Unit U1-U14 | `mkdir -p ../docs/testing/real_run && pytest tests/test_workbook_unit.py -v --cov=app --cov-report=term \| tee ../docs/testing/real_run/unit_output.txt` | 0 | Pass/Fail per ID, and the coverage % at the bottom of the sheet |
| 2 | 2_Unit U15-U17 | `python real_run/api_checks.py \| tee ../docs/testing/real_run/api_checks.txt` | 3 | Pass/Fail and actual result |
| 3 | 6_RAG_Eval and 5_Performance runs 1-30 | first `python real_run/run_question_set.py YOUR.xlsx --limit 3`, then the same without `--limit` | 2 per question | Writes a filled **copy** in `results/`. Then read each answer and fill column J (Correct / Partly / Wrong) yourself |
| 4 | 5_Performance, document processing | `python real_run/run_ingestion_timing.py HR_Policy.pdf ...` | 1 embedding call per 50 chunks | One row per document (also gives I4 evidence if one file has 60+ chunks) |
| 5 | 5_Performance, several users | `python real_run/run_concurrency.py "one question from your list"` | 36 (1+5+10+20 users) | The four rows. Use `--levels 1 5 10` if you want fewer calls |

Questions for step 3: fill columns A-F of sheet 6 first (ID, EN/KIN, question, answerable yes/no, correct answer, expected document).
Write 40 if the sheet asks for 40: about 25 answerable (some Kinyarwanda), about 10 not in the documents, and 5 follow-ups or tricky ones.
Columns K-N (Ragas) are left empty on purpose; see "Metrics" below.

## 4. Done by hand in the app (no scripts needed, few or no Gemini calls)
- **1_Environment**: Mac model, macOS, RAM, browser versions, `docker compose version`, the commit id (`git rev-parse --short HEAD`).
- **3_Validation FR1-FR14**: perform each scenario in the web app, write what happened, fill Pass/Fail. Screenshots go in your own evidence folder (sheet 11 lists the file names), not in the thesis.
- **4_Integration I1-I12**: I1, I3, I9, I10, I11 are done in the web app; I2, I5, I6 with `/docs` or `psql`; I7 and I12 are covered by one question each; I8 by saving a wrong key once and asking one question (one failed call).
- **5_Performance browser table**: open login, upload, chat and analytics in each browser or phone and tick them.
- **8_Protocol, 9_SUS, 10_Survey**: see "Survey" below.

## 5. What to send back to me
1. The filled workbook (with column J filled in).
2. `docs/testing/real_run/unit_output.txt`, `api_checks.txt`, and the printed tables from steps 4 and 5.
3. Your Google Form export (all responses at the time) and a note on how many participants and what roles.
4. Your Mac details and anything that failed or surprised you.
That is all I need to write Chapter 4.5 and Chapter 5.

## Metrics: what is defended and what is not
- Defended and cheap: pass rates, response times (average, median, slowest, 95th percentile), % answered when it should, % correctly declined,
  % Correct / Partly / Wrong by your own marking, expected source cited (computed automatically), documents processed, errors under load.
- Not collected: Ragas faithfulness, relevancy, context precision and recall. They need many extra Gemini calls and you could not defend
  numbers you did not check by hand. Leave K-N empty and say in the chapter that answers were marked manually. Confirm with your supervisor.
- The earlier fake-provider results (267 automated checks) are software-correctness evidence only. They say nothing about answer quality.
