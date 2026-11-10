# Screenshots

Add PNG screenshots here with **exactly these names**. They appear in the README and, in alphabetical order (up to 6), as Figure 3 in the technical report after you run `python docs/report/build_report.py`.

| File | Screen to capture |
|---|---|
| `01_landing_page.png` | Public home page (http://localhost:3000) |
| `02_request_form.png` | Applicant: company request form |
| `03_review_screen.png` | SuperAdmin: reviewing a request (comment box + Approve / Request info / Reject) |
| `04_rag_configuration.png` | SuperAdmin: RAG Configuration, Languages tab with the language check result |
| `05_documents_pipeline.png` | Company admin: Knowledge base with documents processing / ready |
| `06_employee_chat.png` | Employee: a Kinyarwanda or English question with the answer and sources |

Optional extras (not included in the report grid): `07_company_analytics.png`, `08_onboarding_terms.png`, `09_end_service_dialog.png`.

Tips: use a 1440 x 900 window, English interface, and hide real personal data (emails, phone numbers). On macOS: Cmd+Shift+4 then Space, click the window.

> **Note.** `01`, `04`, `05` and `06` were captured automatically from the running app by `backend/tests/e2e_browser.py` using the **test AI providers**, so the chat answer is the test model's. Replace them with your own screenshots (same file names) taken with real Gemini before submitting. `02` and `03` (request form, review screen) still need to be captured by hand.
