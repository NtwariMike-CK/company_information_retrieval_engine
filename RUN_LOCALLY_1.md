# Run everything on macOS (Docker)

## 1. Install Docker Desktop
Download Docker Desktop for Mac (Apple Silicon or Intel), open it and wait until it says "running".
Check in Terminal: `docker --version` and `docker compose version`.
Ports 3000 (website), 8000 (API) and 5432 (database) must be free. If you run Postgres locally, stop it first (`brew services stop postgresql`).

## 2. Unzip and configure
```bash
unzip company-rag.zip && cd company-rag
cp .env.example .env
open -e .env            # or: nano .env   (.env is a hidden file: Finder shows it with Cmd+Shift+.)
```
Fill in at least:
| Variable | Value |
|---|---|
| `POSTGRES_PASSWORD` | any password |
| `JWT_SECRET` | `openssl rand -hex 32` |
| `SECRETS_ENCRYPTION_KEY` | `openssl rand -base64 32 \| tr '+/' '-_'` (44 characters ending in `=`). Never change it after saving API keys. |
| `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` | your platform login (used once, on first start) |
| `EMBED_PAUSE_SECONDS` | `12` if you use Google's free tier (avoids rate-limit failures), otherwise `0` |
Leave `APP_DB_PASSWORD=change_me_app` for local use. Put passwords containing `$` or `#` in quotes.

## 3. Start
```bash
docker compose up --build -d
docker compose logs -f backend      # wait for "Application startup complete", then Ctrl+C
```
The first build takes several minutes. Then open:
- App: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs

## 4. First-time setup (SuperAdmin)
1. Sign in at http://localhost:3000/login with your SUPERADMIN email and password.
2. **RAG Configuration -> API credentials -> Add key**: paste your Google AI Studio key.
3. **LLM** tab: model `gemini-3.8-flash` -> **Validate & activate**.
4. **Embedding** tab: model `gemini-embedding-2` -> **Validate & activate**. Set batch size 20 on the free tier.
5. **Chunking** tab (free tier): child 800, parent 2400 -> **Validate & activate**.
6. **Languages** tab -> **Run check** to see whether English/Kinyarwanda retrieval works with your models.

## 5. Try the full flow (use a private window per role)
The login is stored per browser, so use separate browsers/private windows for SuperAdmin, company admin and employee.
- **New-company flow:** private window -> http://localhost:3000 -> Request access -> create account -> fill the request. SuperAdmin -> Company requests -> Approve. Applicant -> Onboarding (3 pages) -> accept terms -> you land in the admin dashboard.
- **Or manual:** SuperAdmin -> Companies -> Add company.
- Company admin: **Employees** (add one) -> **Knowledge base** (upload PDF/DOCX/TXT/MD, wait until it turns green) -> **Start**.
- Employee: sign in (another private window) -> ask questions in English or Kinyarwanda.

## Everyday commands
| Do | Command |
|---|---|
| Stop (keeps data) | `docker compose stop` |
| Start again | `docker compose start` |
| See logs | `docker compose logs -f backend` |
| After changing code or `.env` | `docker compose up --build -d` |
| Wipe everything (database + files) | `docker compose down -v` |

## If you already have data from the previous version
```bash
docker compose stop backend
docker compose up -d db
docker compose exec -T db psql -U rag_owner -d company_rag < db/migrations/002_onboarding_multilingual.sql
docker compose up --build -d
```

## Troubleshooting
- **"port is already allocated"**: another program uses 3000/8000/5432. Quit it, or change the left side of the port in `docker-compose.yml`.
- **Cannot sign in as SuperAdmin**: the account is created once, on the very first start. If you changed `.env` afterwards, run `docker compose down -v` and start again (wipes data).
- **A document shows "failed"**: `docker compose exec db psql -U rag_owner -d company_rag -x -c "select stage, error_detail from processing_jobs order by created_at desc limit 1;"`. Most often: no API key saved yet, or a Google rate limit (set `EMBED_PAUSE_SECONDS=12`, rebuild, click Retry).
- **Website cannot reach the API**: `NEXT_PUBLIC_API_URL` is baked in at build time; after changing it run `docker compose up --build -d`.
- **Emails**: not needed locally. Without `SMTP_HOST` they are only recorded and every message still appears in the portal.
