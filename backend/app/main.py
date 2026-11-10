import asyncio, logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from .db import pool, q1, tx
from .routers import apply, applications_admin, auth, chat, cms, company_admin, model_eval, public, superadmin
from .security import assert_production_safe
from .seed import seed
from .settings import settings
from .worker import run_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_production_safe()
    await pool.open()
    await pool.wait()
    await seed()
    stop, task = asyncio.Event(), None
    if settings.embedded_worker:
        task = asyncio.create_task(run_worker(stop))
    yield
    stop.set()
    if task:
        try:
            await asyncio.wait_for(task, 10)
        except asyncio.TimeoutError:
            task.cancel()
    await pool.close()


app = FastAPI(
    title="Company RAG Chatbot API",
    version="1.2.0",
    description="Multi-tenant RAG chatbot. **Authorize** with the token from `POST /auth/login`. "
                "Roles: SuperAdmin, Company Admin, Employee. Errors: `{detail: {code, message}}`.",
    lifespan=lifespan,
    openapi_tags=[{"name": "Public"}, {"name": "Auth"}, {"name": "Company Request (Applicant)"}, {"name": "SuperAdmin"}, {"name": "SuperAdmin - Company Requests"}, {"name": "SuperAdmin - Content & Languages"}, {"name": "SuperAdmin - Model Evaluation"}, {"name": "Company Admin"}, {"name": "Employee Chat"}, {"name": "Health"}],
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for r in (public.router, auth.router, apply.router, superadmin.router, applications_admin.router, cms.router, model_eval.router, company_admin.router, chat.router):
    app.include_router(r)


@app.exception_handler(UniqueViolation)
async def _unique(_: Request, exc: UniqueViolation):
    return JSONResponse(status_code=409, content={"detail": {"code": "conflict", "message": "A record with these details already exists (e.g. duplicate email or company name)."}})


@app.exception_handler(ForeignKeyViolation)
async def _fk(_: Request, exc: ForeignKeyViolation):
    return JSONResponse(status_code=409, content={"detail": {"code": "conflict", "message": "This record is referenced by other data."}})


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception):
    logging.getLogger("app").exception("unhandled error")      # technical detail stays in logs
    return JSONResponse(status_code=500, content={"detail": {"code": "internal_error", "message": "Something went wrong. Please try again."}})


@app.get("/health", tags=["Health"])
async def health():
    async with tx() as conn:
        await q1(conn, "SELECT 1")
    return {"status": "ok"}
