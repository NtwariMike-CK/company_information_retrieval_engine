import time
from collections import defaultdict

from fastapi import APIRouter, Request

from ..db import q, q1, tx
from ..errors import err
from ..schemas import RegisterIn
from ..settings import settings
from ..security import create_token, hash_password
from ..services.applications import CURRENT_STEPS_SQL

router = APIRouter(prefix="/public", tags=["Public"])
_reg: dict[str, list[float]] = defaultdict(list)    # simple per-IP registration throttle (per instance)


@router.get("/site-content", summary="Landing page sections (editable by the SuperAdmin)")
async def site_content():
    async with tx() as conn:
        return await q(conn, "SELECT key, label, content, position FROM site_content WHERE is_active ORDER BY position, key")


@router.get("/legal", summary="Current data-handling pages and terms (what admins accept)")
async def legal():
    async with tx() as conn:
        return await q(conn, CURRENT_STEPS_SQL)


@router.get("/languages", summary="Languages the assistant supports")
async def languages():
    async with tx() as conn:
        return await q(conn, "SELECT code, name, native_name FROM languages WHERE is_enabled ORDER BY position, code")


@router.post("/register", status_code=201, summary="Create an applicant account (step 1 of requesting access for a company)")
async def register(body: RegisterIn, request: Request):
    ip = request.client.host if request.client else "?"
    now = time.time()
    _reg[ip] = [t for t in _reg[ip] if now - t < 3600]
    if len(_reg[ip]) >= settings.register_limit_per_hour:
        raise err(429, "too_many_attempts", "Too many registrations from this network. Please try again later.")
    async with tx() as conn:
        if await q1(conn, "SELECT 1 FROM users WHERE email = %s", body.email):
            raise err(409, "email_taken", "An account with this email already exists. Please sign in instead.")
        u = await q1(conn, """INSERT INTO users (role, full_name, phone, email, password_hash)
                              VALUES ('applicant', %s, %s, %s, %s) RETURNING id, full_name, email, role""",
                     body.full_name, body.phone, body.email, hash_password(body.password))
    _reg[ip].append(now)
    return {"access_token": create_token(u["id"], "applicant", None), "token_type": "bearer",
            "user": {**u, "company_id": None, "company_name": None}}
