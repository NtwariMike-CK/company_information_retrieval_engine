import logging
from psycopg.types.json import Jsonb

from ..db import ex, q1, tx

log = logging.getLogger("app")


async def audit(conn, actor_id, action, company_id=None, target_type=None, target_id=None, details=None):
    """Never pass secrets in details."""
    await ex(conn, """INSERT INTO audit_logs (company_id, actor_id, action, target_type, target_id, details)
                      VALUES (%s,%s,%s,%s,%s,%s)""", company_id, actor_id, action, target_type,
             str(target_id) if target_id else None, Jsonb(details or {}))


async def log_error(source: str, code: str | None, message: str, detail: str | None = None, company_id=None):
    """Technical details go to protected logs only; users see safe messages."""
    log.error("%s/%s: %s | %s", source, code, message, detail)
    try:
        async with tx(bypass=True) as conn:
            await ex(conn, "INSERT INTO error_logs (company_id, source, error_code, message, detail) VALUES (%s,%s,%s,%s,%s)",
                     company_id, source, code, message[:500], (detail or "")[:4000])
    except Exception:
        log.exception("failed to write error_logs")


async def recompute_kb_status(conn, company_id):
    r = await q1(conn, """SELECT count(*) AS total,
                                 count(*) FILTER (WHERE status IN ('uploaded','processing')) AS busy,
                                 count(*) FILTER (WHERE status = 'failed') AS failed
                          FROM documents WHERE company_id = %s""", company_id)
    status = "empty" if r["total"] == 0 else "processing" if r["busy"] else "failed" if r["failed"] else "ready"
    await ex(conn, "UPDATE companies SET kb_status = %s WHERE id = %s", status, company_id)
    return status
