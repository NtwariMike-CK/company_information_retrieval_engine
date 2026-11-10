# Backend (FastAPI)

## Run locally with Docker (recommended)
```bash
cp .env.example .env            # repo root; set JWT_SECRET and SECRETS_ENCRYPTION_KEY
docker compose up --build
```
- API: http://localhost:8000 · **Swagger UI: http://localhost:8000/docs** · ReDoc: `/redoc`
- First start seeds: SuperAdmin (`SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD`), a default RAG config, 2 default evaluation questions.

## First-time setup flow (as SuperAdmin)
1. `POST /auth/login` -> token. Click **Authorize** in Swagger.
2. `POST /superadmin/credentials` -> add your Google AI Studio key (stored encrypted, never returned).
3. `PUT /superadmin/rag-config` -> set `llm_cfg.model` to the exact Gemini model id from AI Studio. The change is **live-tested** (a real embedding + LLM call) before activation; on failure the previous config stays active.
4. `POST /superadmin/companies` -> company + first admin. Company admin then logs in, adds employees, uploads documents, waits for `kb_status = ready`, calls `POST /company/service/start`.

## Postman
Import `postman/company-rag.postman_collection.json`. Run **Auth > Log in**; the token is saved to `{{token}}` automatically. Regenerate after API changes:
`cd backend && python scripts/export_postman.py ../postman/company-rag.postman_collection.json`

## Local dev without Docker / without a Gemini key
Set `embedding_cfg.provider` and `llm_cfg.provider` to `"fake"` via `PUT /superadmin/rag-config` (deterministic stand-in models) to exercise the whole pipeline offline.

## Company onboarding flow (v1.1)
`POST /public/register` -> applicant account -> `POST /apply/applications` (form defined in the database) -> SuperAdmin reviews at `/superadmin/applications/{id}/decision` (`approve`, `reject` + comment, `request_info` + comment) -> applicant replies via `/apply/applications/{id}/respond` -> on approval `GET /apply/onboarding` returns the 3 pages -> `POST /apply/onboarding/complete` (accept the current terms version) creates the company and turns the applicant into its `company_admin`. Rejected applicants can submit again; only one request can be open at a time.

Emails are queued in `email_outbox`; set `SMTP_*` in `.env` to actually send them. Without SMTP they are recorded as `skipped` and everything still works through the portal.

Public (no login): `/public/site-content`, `/public/legal`, `/public/languages`, `/public/register`.
Content managed by the SuperAdmin (all in the database): `/superadmin/site-content`, `/superadmin/onboarding-steps` (versioned), `/superadmin/application-fields`, `/superadmin/languages` (+ `POST /superadmin/languages/check`).
Company admin extras: `GET /company/request`, `GET /company/export` (ZIP of all company data).

## Tests
```bash
python tests/smoke.py            # 51 checks (v1.0 behaviour)
python tests/smoke_v11.py        # 75 checks (v1.1: onboarding, CMS, languages, export, anonymisation)
python tests/test_language.py    # 9 unit tests, no database
```

## Module map
| Path | Responsibility |
|---|---|
| `app/routers/` | `auth`, `superadmin`, `company_admin`, `chat` endpoints |
| `app/rag/extract.py` `clean.py` `chunking.py` | Pluggable ingestion steps (+EDA stats) |
| `app/rag/ai.py` | Embedding + LLM providers (`google`, `fake`); add a provider = add a class |
| `app/rag/retrieval.py` | Dense + sparse search, RRF fusion, query-transform slot, reranker slot |
| `app/services/chat.py` | The question -> answer workflow, evidence logging |
| `app/services/ingest.py` / `deletion.py` / `worker.py` | Background jobs (Postgres queue, `FOR UPDATE SKIP LOCKED`) |

## Security notes
- Passwords: Argon2. API keys: Fernet-encrypted at rest, never in any response. JWT carries identity; `company_id` always comes from the DB user row, never from request input.
- RLS is enforced because the API connects as the non-owner role `rag_app`. **Change its password** (`ALTER ROLE rag_app PASSWORD '...'`) in every real environment.
- Login is throttled per IP+email (in-memory, per instance).
