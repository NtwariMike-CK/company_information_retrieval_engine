# Company RAG Chatbot

A **multi-tenant, bilingual (English + Kinyarwanda) Retrieval-Augmented Generation platform**. Companies upload their own documents; their employees ask questions in natural language and receive grounded answers, with the source documents, from a large language model. Each company's data is isolated from every other company's.

| Submission item | Link |
|---|---|
| Source code (this repository) | **[ADD GITHUB REPOSITORY LINK]** |
| Technical walkthrough video | **[ADD VIDEO LINK]** |
| Technical report (PDF, 5 pages max) | **[ADD PUBLIC LINK]**, also in this repo: [`docs/Technical_Report.pdf`](docs/Technical_Report.pdf) |
| Scope alignment & feature validation | [`docs/SCOPE_ALIGNMENT.md`](docs/SCOPE_ALIGNMENT.md) / [PDF](docs/Scope_Alignment_and_Feature_Validation.pdf) |

> **Quick start:** `cp .env.example .env`, fill in the secrets, then `docker compose up --build -d` and open http://localhost:3000. Details in [Installation](#installation-and-running) and [`RUN_LOCALLY.md`](RUN_LOCALLY.md).

## Contents
1. [Project overview](#project-overview) · 2. [Screenshots](#screenshots) · 3. [Architecture](#architecture) · 4. [Technical requirements](#technical-requirements) · 5. [Installation and running](#installation-and-running) · 6. [Using the application](#using-the-application) · 7. [Configuration](#configuration) · 8. [Repository structure](#repository-structure) · 9. [API documentation](#api-documentation) · 10. [Testing](#testing) · 11. [Security and privacy](#security-and-privacy-design) · 12. [Scope status](#scope-status) · 13. [Limitations and future work](#limitations-and-future-work)

## Project overview
**Problem.** Employees lose time searching policies, procedures and manuals. General chatbots do not know a company's documents and may invent answers.

**Solution.** Each company uploads its documents. The platform cleans, splits, embeds and indexes them. When an employee asks a question, the system retrieves the most relevant passages (hybrid vector + keyword search), asks the LLM to answer **only from those passages**, and falls back to a configurable "I could not find this" response when the documents do not contain the answer.

**Roles**
| Role | Can do |
|---|---|
| **Visitor / Applicant** | Read the public site, create an account, request access for a company, reply to the reviewer, complete onboarding (data guidelines, privacy summary, terms) |
| **SuperAdmin** | Configure the global RAG pipeline and API keys, review company requests (approve / reject with comment / request more information), manage companies, evaluation questions, landing-page and onboarding content, languages, platform analytics |
| **Company Admin** | Manage employees, upload documents and watch processing, start / pause / end the service (end deletes all company data), analytics, exports, download all data |
| **Employee** | Chat (up to 9 question-answer exchanges per chat), rate answers, report issues, browse chat history |

**Highlights**
- English and Kinyarwanda: language-aware cleaning/chunking, bilingual keyword search, multilingual embeddings, answers in the language of the question, and a built-in **Language check** that tests the configured models.
- Hybrid retrieval: pgvector HNSW (dense) + PostgreSQL full-text (sparse) fused with Reciprocal Rank Fusion; parent-child chunking.
- Safe configuration: every change is live-tested before activation; the last working configuration stays active on failure; versions and rollback.
- Strong tenant isolation: `company_id` on every record, backend scoping, and PostgreSQL row-level security.
- Complete data lifecycle: pause (keep data) vs end (tracked, retried deletion of everything incl. employee accounts), data export before ending, de-identified rating statistics kept.
- Content managed in the database (landing page, onboarding pages with versioned terms, request-form fields, languages), not in code.

## Screenshots
| | |
|---|---|
| ![Landing page](docs/screenshots/01_landing_page.png) | ![Request form](docs/screenshots/02_request_form.png) |
| ![Review screen](docs/screenshots/03_review_screen.png) | ![RAG configuration](docs/screenshots/04_rag_configuration.png) |
| ![Documents pipeline](docs/screenshots/05_documents_pipeline.png) | ![Employee chat](docs/screenshots/06_employee_chat.png) |

## Architecture
```mermaid
flowchart LR
  B["Browser<br/>Next.js 14 (Vercel)"] -- "REST + JWT" --> A["FastAPI backend (Render)<br/>routers -> services -> rag"]
  A -- "SQL + row-level security" --> D[("PostgreSQL 16 + pgvector")]
  A -- "embeddings + LLM" --> G["Google Gemini API"]
  A --> W["Background worker<br/>ingest / delete / email"]
  W --> D
  W --> G
  W --> S[("Uploaded files (disk)")]
```
**Answering a question:** validate -> detect language -> (query transform) -> embed -> dense search + sparse search -> RRF fusion -> evidence check -> expand to parent chunks -> prompt with language directive -> LLM -> store answer, scores and retrieved chunks -> ask for feedback.

**Ingesting a document:** extract (PDF / DOCX / TXT / MD) -> clean + EDA statistics -> language-aware chunking -> embeddings (batched, retried, paced) -> HNSW + GIN index -> mark ready.

Database design: [`db/DATABASE.md`](db/DATABASE.md) (33 tables, ER diagrams). Technical details and algorithms: technical report, Section 3.

## Technical requirements
**Software**
| Component | Version / detail |
|---|---|
| Docker Desktop (Docker Engine + Compose v2) | any recent version (macOS, Windows, Linux) |
| Backend | Python 3.12, FastAPI >= 0.121 (tested with 0.162), Uvicorn, psycopg 3 + pool, Pydantic 2, argon2-cffi, PyJWT, cryptography (Fernet), httpx, pypdf, python-docx |
| Database | PostgreSQL 16 with extensions `pgvector`, `pgcrypto`, `citext` (Docker image `pgvector/pgvector:pg16`; development tests also ran on pgvector 0.6.0) |
| Frontend | Next.js 14.2.35, React 18.3, TypeScript 5.5, Tailwind CSS 3.4, lucide-react, react-markdown, Geist font (Docker uses Node 20; production build also verified with Node 22) |
| AI services | Google Gemini API (Google AI Studio key): `gemini-3.8-flash` (answers), `gemini-embedding-2` (768-dimension embeddings). A billing-enabled Google project is recommended for real company data |
| Browsers | current Chrome, Safari, Firefox, Edge (results: technical report, Section 5.2) |

**Hardware**
- Minimum: 2 CPU cores, 4 GB RAM available to Docker, 5 GB free disk.
- Recommended: 4 cores, 8 GB RAM.
- Measured: the API process uses about 80 MB idle and 180 MB under 10 simultaneous chat users; a 1-vCPU / 4 GB VM sustained 10 simultaneous users without errors (technical report, Section 5). AI response time depends on Google, not on your hardware.

## Installation and running
### Option A: Docker (recommended)
```bash
git clone <repository-url> company-rag && cd company-rag
cp .env.example .env
```
Edit `.env` and set:
```bash
openssl rand -hex 32                          # -> JWT_SECRET
openssl rand -base64 32 | tr '+/' '-_'        # -> SECRETS_ENCRYPTION_KEY (44 characters, ends with "=")
# also: POSTGRES_PASSWORD, SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD
# EMBED_PAUSE_SECONDS=12 if you use Google's free tier
```
```bash
docker compose up --build -d
docker compose logs -f backend        # wait for "Application startup complete"
```
Open **http://localhost:3000** (app) and **http://localhost:8000/docs** (Swagger). Sign in with `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD`. macOS step-by-step, troubleshooting and upgrade notes: [`RUN_LOCALLY.md`](RUN_LOCALLY.md).

### Option B: development mode (without Docker for the apps)
1. PostgreSQL 16 with pgvector running locally; create a database, then `psql -d <db> -f db/schema.sql`.
2. Backend:
```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://rag_app:change_me_app@localhost:5432/company_rag
export JWT_SECRET=dev-secret SUPERADMIN_EMAIL=admin@example.com SUPERADMIN_PASSWORD='ChangeMe123!'
uvicorn app.main:app --reload --port 8000
```
3. Frontend: `cd frontend && cp .env.example .env.local && npm install && npm run dev` (http://localhost:3000).

### First-time setup (SuperAdmin)
1. **RAG Configuration -> API credentials**: add the Google AI Studio key.
2. **LLM** tab: model `gemini-3.8-flash`. **Embedding** tab: `gemini-embedding-2`. Click **Validate & activate** (a live test call is made).
3. **Languages** tab: **Run check** to verify English / Kinyarwanda retrieval with your models.
No key yet? Set the embedding and LLM providers to `fake` for an offline demo with deterministic stand-in models.

## Using the application
- **New company (public flow):** home page -> Request access -> create account -> fill the request -> SuperAdmin reviews -> applicant completes the 3-page onboarding and accepts the terms -> the company workspace opens.
- **Company admin:** add employees -> upload documents (wait for green) -> Start.
- **Employee:** ask questions in English or Kinyarwanda; rate answers when asked; use Report to send feedback.
- **Ending the service:** Company admin -> Dashboard -> End service (type END). Download your data first.

## Configuration
Environment variables (`.env`, see `.env.example`):
| Variable | Purpose |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `APP_DB_PASSWORD` | Database credentials (the API connects as the non-owner role `rag_app` so row-level security applies) |
| `JWT_SECRET`, `SECRETS_ENCRYPTION_KEY` | Token signing; encryption of stored API keys (required in production) |
| `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD` | First SuperAdmin (created once, on first start) |
| `EMBED_PAUSE_SECONDS` | Pause between embedding batches (use 12 on Google's free tier) |
| `FRONTEND_URL`, `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL` | URLs used for links and cross-origin access |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `NOTIFY_EMAIL` | Optional email delivery (without SMTP, emails are recorded as "skipped") |
| `REGISTER_LIMIT_PER_HOUR`, `ENVIRONMENT` | Sign-up throttle; `production` enables strict secret checks |
RAG settings (chunking, retrieval, models, prompts, error messages, limits) are **not** environment variables: the SuperAdmin edits them in the application.

## Repository structure
```
company-rag/
├── docker-compose.yml            # db + backend + frontend
├── .env.example                  # configuration template
├── RUN_LOCALLY.md                # macOS run guide
├── db/
│   ├── schema.sql                # full schema for fresh installs (33 tables)
│   ├── migrations/               # idempotent upgrade scripts: 002 (onboarding, languages), 003 (model evaluation)
│   └── DATABASE.md               # table reference + ER diagrams
├── backend/
│   ├── Dockerfile, requirements.txt
│   ├── app/
│   │   ├── main.py               # app, middleware, error handlers, lifespan (seed + worker)
│   │   ├── settings.py, db.py, security.py, deps.py, errors.py, schemas.py
│   │   ├── routers/              # HTTP layer: auth, public, apply, superadmin, applications_admin, cms, model_eval, company_admin, chat
│   │   ├── services/             # business logic: chat, ingest, deletion, config_service, analytics, applications, mailer, common
│   │   ├── rag/                  # pipeline parts: extract, clean, chunking, lang, retrieval, ai (embedding + LLM providers)
│   │   ├── eval/                 # model evaluation lab: metrics (pure functions), LLM judge, starter benchmark, runner
│   │   ├── worker.py             # PostgreSQL-backed job worker
│   │   └── seed.py, seed_content.py   # first-start data (SuperAdmin, config, languages, content)
│   ├── tests/                    # unit (3 files), integration (smoke*, REST, data-flow trace), e2e_browser.py, benchmark.py, run_all_tests.sh
│   └── scripts/export_postman.py
├── frontend/
│   ├── Dockerfile, package.json, tailwind.config.ts
│   └── src/
│       ├── app/                  # pages: / (landing), login, register, legal, apply/*, admin/*, superadmin/*, chat
│       ├── components/           # ui primitives, shell/layout, marketing, application form, charts, markdown
│       └── lib/                  # typed API client, auth context
├── postman/                      # Postman collection (109 requests)
└── docs/
    ├── Technical_Report.pdf, SCOPE_ALIGNMENT.md, Scope_Alignment_and_Feature_Validation.pdf
    ├── TESTING_REPORT.md / Testing_Report.pdf       # Chapter 4.5: environments, unit, validation, integration, system, acceptance
    ├── MODEL_EVALUATION_METRICS.md / .pdf           # explains every metric on the SuperAdmin Model evaluation page
    ├── SYSTEM_DOCUMENTATION.md / .pdf               # how each part works (upload, cleaning, chunking, embedding, retrieval, LLM) + Q&A
    ├── testing/                  # logs/, results/, screenshots/, acceptance/ (SUS kit)
    ├── report/                   # sources + build_report.py that regenerate the documents
    ├── screenshots/, figures/, benchmark_results_*.json
```

## API documentation
- **Swagger UI:** http://localhost:8000/docs (click *Authorize* and paste the token from `POST /auth/login`).
- **Postman:** import `postman/company-rag.postman_collection.json`; *Auth -> Log in* stores the token automatically. Regenerate with `python backend/scripts/export_postman.py postman/company-rag.postman_collection.json`.
- 109 operations in 10 groups: Public, Auth, Company Request (Applicant), SuperAdmin, SuperAdmin - Company Requests, SuperAdmin - Content & Languages, SuperAdmin - Model Evaluation, Company Admin, Employee Chat, Health. Errors always use `{"detail": {"code", "message", "fields"?}}`.

## Testing
Full report: [`docs/TESTING_REPORT.md`](docs/TESTING_REPORT.md) (Chapter 4.5). Evidence (logs, results, screenshots): [`docs/testing/`](docs/testing/). The tests use deterministic test AI providers, so no Gemini key is needed, and they **switch the global AI configuration**: run them only on a throwaway stack (`docker compose down -v`).
```bash
cd backend
bash tests/run_all_tests.sh        # everything below in one go (starts the API under coverage)
# or one at a time, with the API running (REGISTER_LIMIT_PER_HOUR=1000):
pytest tests/test_language.py tests/test_eval_metrics.py tests/test_security_and_pipeline.py -v   # 39 unit tests, no database
python tests/smoke.py              # 51 checks: core platform
python tests/smoke_v11.py          # 76 checks: onboarding, CMS, languages, export, anonymisation, concurrency
python tests/smoke_eval.py         # 40 checks: model evaluation lab
python tests/rest_interface_samples.py   # 32 REST requests, expected vs actual, plus error-tracking evidence
python tests/data_flow_trace.py    # one document + questions traced through API, worker, database, deletion
python tests/e2e_browser.py ../docs/testing/screenshots   # 29 Playwright checks + screenshots (front end on :3000)
python tests/benchmark.py --part all    # latency, concurrency, ingestion, retrieval scaling, CPU/memory
```
**Result: 267 automated checks, all passing; 84% statement coverage of the API with all suites running; 86% branch coverage of the core logic modules.** Real defects found and fixed are listed in the testing report (4.5.3). **Still to do on your own hardware:** Gemini evaluation runs, Safari/Firefox/real-device checks, and acceptance testing with 20+ participants (kit in `docs/testing/acceptance/`).

### Model evaluation (SuperAdmin > Model evaluation)
Evaluates the embedding/retrieval part and the LLM separately on a benchmark you control (starter set: 21 questions, English + Kinyarwanda): Hit@k, MRR, nDCG, MAP, evidence integrity, cross-language gap, no-answer threshold (precision/recall/F1), key-fact recall, faithfulness, language match, abstention, with keyword-only and no-documents baselines. See [`docs/MODEL_EVALUATION_METRICS.md`](docs/MODEL_EVALUATION_METRICS.md).

## Security and privacy design
- Passwords: Argon2. API keys: encrypted at rest (Fernet), never returned to the browser. Login throttling. Parameterised SQL. CSV-formula neutralisation in exports.
- Role-based access on every endpoint; the company is always taken from the authenticated user, never from request input.
- Isolation: `company_id` everywhere + PostgreSQL row-level security (FORCE, so it also binds the table owner).
- Deletion: six tracked, retryable steps; only de-identified rating scores and report categories are kept.
- **Important:** on Google's free Gemini tier, submitted content may be used to improve Google products. Use a billing-enabled key for real company data. The terms shown to company admins are a starting draft and should be reviewed before real use.

## Scope status
See [`docs/SCOPE_ALIGNMENT.md`](docs/SCOPE_ALIGNMENT.md): every planned feature with purpose, status (completed / partial / not implemented) and evidence, plus the justified scope changes. At the time of writing, 30 of 36 features are completed, 4 partial and 2 not implemented (cloud deployment, and the future-work items).

## Limitations and future work
No OCR for scanned PDFs; answers are not streamed; no reranking model; email is outbound only; backups and retention rely on the hosting provider; login throttling and file storage are per instance. Planned: cloud deployment (Render + Vercel), billing per usage, image understanding, marketing emails.

## Author
**[YOUR NAME]**, [PROGRAMME, UNIVERSITY]. Supervisor: [SUPERVISOR NAME]. Academic project; all rights reserved unless a licence file is added.
