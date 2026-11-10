from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import q1, tx
from .errors import err
from .security import decode_token

bearer = HTTPBearer(auto_error=False, description="JWT from POST /auth/login")


async def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not creds:
        raise err(401, "not_authenticated", "Authentication required.")
    payload = decode_token(creds.credentials)
    async with tx() as conn:
        u = await q1(conn, """SELECT u.id, u.company_id, u.role, u.full_name, u.email, u.status,
                                     c.access_status AS company_access, c.name AS company_name
                              FROM users u LEFT JOIN companies c ON c.id = u.company_id WHERE u.id = %s""",
                     payload["sub"])
    if not u or u["status"] != "active":
        raise err(401, "account_inactive", "This account is inactive.")
    if u["role"] in ("company_admin", "employee") and u["company_access"] != "active":
        raise err(403, "company_inactive", "Your company's access to the service has been deactivated.")
    u["impersonator"] = payload.get("imp")
    return u


def tenant(*roles: str):
    """Dependency factory -> yields (user, conn). conn is inside a transaction with the RLS
    context set from the *authenticated user* (never from request input)."""
    async def dep(user: dict = Depends(current_user)):
        if user["role"] not in roles:
            raise err(403, "forbidden", "You do not have permission to perform this action.")
        async with tx(company_id=user["company_id"], bypass=user["role"] == "super_admin") as conn:
            yield user, conn
    return dep


def role_user(*roles: str):
    """Like tenant(), but returns only the user and holds NO database connection. Use it for slow endpoints
    (AI calls) that open their own short transactions: holding a pooled connection for the whole request
    while also needing a second one starves the pool under concurrency."""
    async def dep(user: dict = Depends(current_user)):
        if user["role"] not in roles:
            raise err(403, "forbidden", "You do not have permission to perform this action.")
        return user
    return dep


SA = tenant("super_admin")
SA_USER = role_user("super_admin")
EMP_USER = role_user("employee")
CA = tenant("company_admin")
EMP = tenant("employee")
