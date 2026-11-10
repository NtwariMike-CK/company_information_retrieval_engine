# Frontend (Next.js 14, TypeScript, Tailwind)

Dark theme in blue / white / black, Geist font (bundled, no external font requests).

## Run locally
```bash
cd frontend
cp .env.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                     # http://localhost:3000
```
The API must be running (`docker compose up -d db backend` from the repo root) and must allow this origin in `CORS_ORIGINS` (default `http://localhost:3000`).

Sign in with the seeded SuperAdmin (`SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` from `.env`).

## Screens
| Role | Route | What it does |
|---|---|---|
| SuperAdmin | `/superadmin` | Register companies + first admin, activate/deactivate, **Enter as admin**, details |
| | `/superadmin/rag` | Documents, cleaning, chunking, embedding, retrieval, LLM, prompts, error messages, chat limit, **API credentials** (add / replace / disable / delete), version history + rollback |
| | `/superadmin/evaluation` | When feedback is requested; add/edit/delete 1-5 and True/False questions |
| | `/superadmin/analytics` | Platform or per-company analytics, frequent questions, feedback, reported cases (status workflow) |
| Company Admin | `/admin` | Green/amber/red knowledge-base status, **Start / Pause / End** (End needs typing `END`), live deletion progress |
| | `/admin/documents` | Drag-and-drop upload, per-stage pipeline progress (auto-refresh), EDA stats, retry, delete |
| | `/admin/employees` | Create/edit employees, role, status, password reset |
| | `/admin/analytics` | Feedback, reported cases, questions (+CSV), conversations with evidence (+CSV of selected/all) |
| Public | `/` , `/register`, `/legal` | Marketing site (content from the database), applicant sign-up, public privacy & terms |
| Applicant | `/apply`, `/apply/onboarding` | Request form, conversation with the reviewer, reply to questions, 3-page onboarding + terms acceptance |
| SuperAdmin (new) | `/superadmin/applications`, `/superadmin/content` | Review requests (approve / reject / request info), edit landing page, onboarding pages (versioned), form fields; Languages tab in RAG Configuration |
| Company Admin (new) | `/admin/request` | The request, its history and the terms accepted; End-service dialog offers a full data download |
| Employee | `/chat` | ChatGPT-style chat, history sidebar, New chat, Report, processing indicator, sources, rating prompt, 9-question limit banner |

## Deploy to Vercel
1. Import the repo, set **Root Directory** to `frontend`.
2. Environment variable: `NEXT_PUBLIC_API_URL=https://<your-render-backend>.onrender.com`
3. On Render set `CORS_ORIGINS=https://<your-vercel-domain>` (comma-separate multiple origins).

## Notes
- The JWT is kept in `localStorage`. This is simple and works across Vercel/Render domains, but is exposed to XSS; the app renders model output with `react-markdown` (no raw HTML) to limit that risk. A stricter setup would use httpOnly cookies behind a same-site proxy.
- "Enter as admin" keeps the SuperAdmin token in `sessionStorage` so one click returns to SuperAdmin; the backend issues a 60-minute, audited token.
