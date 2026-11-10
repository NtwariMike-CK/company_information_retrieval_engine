import time
from collections import defaultdict

from fastapi import APIRouter, Depends, Request

from ..db import ex, q1, tx
from ..deps import current_user
from ..errors import err
from ..schemas import LoginIn, PasswordChangeIn
from ..security import DUMMY_HASH, create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])
_fails: dict[str, list[float]] = defaultdict(list)     # simple in-memory brute-force guard (per instance)
MAX_FAILS, WINDOW = 5, 900


@router.post("/login", summary="Log in (all roles)")
async def login(body: LoginIn, request: Request):
    key = f"{request.client.host if request.client else '?'}:{body.email.lower()}"
    now = time.time()
    _fails[key] = [t for t in _fails[key] if now - t < WINDOW]
    if len(_fails[key]) >= MAX_FAILS:
        raise err(429, "too_many_attempts", "Too many failed attempts. Please try again in 15 minutes.")
    async with tx() as conn:
        u = await q1(conn, """SELECT u.*, c.access_status AS company_access, c.name AS company_name
                              FROM users u LEFT JOIN companies c ON c.id=u.company_id WHERE u.email=%s""", body.email)
        ok = verify_password(u["password_hash"] if u else DUMMY_HASH, body.password)
        if not u or not ok or u["status"] != "active":
            _fails[key].append(now)
            raise err(401, "invalid_credentials", "Invalid email or password.")
        if u["role"] in ("company_admin", "employee") and u["company_access"] != "active":
            raise err(403, "company_inactive", "Your company's access to the service has been deactivated.")
        await ex(conn, "UPDATE users SET last_login_at=now() WHERE id=%s", u["id"])
    _fails.pop(key, None)
    return {"access_token": create_token(u["id"], u["role"], u["company_id"]), "token_type": "bearer",
            "user": {"id": u["id"], "full_name": u["full_name"], "email": u["email"], "role": u["role"],
                     "company_id": u["company_id"], "company_name": u["company_name"]}}


@router.get("/me", summary="Current user")
async def me(user: dict = Depends(current_user)):
    return {k: user[k] for k in ("id", "full_name", "email", "role", "company_id", "company_name", "impersonator")}


@router.post("/change-password", summary="Change own password")
async def change_password(body: PasswordChangeIn, user: dict = Depends(current_user)):
    async with tx() as conn:
        row = await q1(conn, "SELECT password_hash FROM users WHERE id=%s", user["id"])
        if not verify_password(row["password_hash"], body.current_password):
            raise err(400, "wrong_password", "Current password is incorrect.")
        await ex(conn, "UPDATE users SET password_hash=%s WHERE id=%s", hash_password(body.new_password), user["id"])
    return {"ok": True}
