"""'End service' deletion (documents, vectors, conversations, feedback, reports, employee accounts, files, logs): tracked step-by-step, resumable, retried by the worker."""
import shutil
from pathlib import Path

from psycopg.types.json import Jsonb

from ..db import ex, q1, tx
from ..settings import settings
from .common import log_error

STEPS = ("anonymize", "vectors", "database", "files", "temp_files", "logs")
MAX_ATTEMPTS = 5


def company_dir(cid) -> Path:
    return Path(settings.storage_dir) / str(cid)


def temp_dir(cid) -> Path:
    return Path(settings.storage_dir) / "_tmp" / str(cid)


async def process_deletion() -> bool:
    async with tx(bypass=True) as conn:
        job = await q1(conn, """UPDATE deletion_jobs SET status='running', attempts=attempts+1
                                WHERE id = (SELECT id FROM deletion_jobs WHERE status IN ('pending','failed') AND attempts < %s
                                            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""", MAX_ATTEMPTS)
    if not job:
        return False
    cid, steps = job["company_id"], dict(job["steps"])
    try:
        for step in STEPS:
            if steps.get(step) == "done":
                continue
            async with tx(bypass=True) as conn:
                if step == "anonymize":
                    # keep ONLY de-identified scores / report categories for product improvement: no ids, no text, no company, no user
                    await ex(conn, """INSERT INTO anonymised_feedback (recorded_month, kind, evaluation_text, rating, bool_value)
                                      SELECT date_trunc('month', f.created_at)::date, 'rating', eq.text, f.rating, f.bool_value
                                      FROM feedback f JOIN evaluation_questions eq ON eq.id = f.question_id WHERE f.company_id = %s""", cid)
                    await ex(conn, """INSERT INTO anonymised_feedback (recorded_month, kind, report_type)
                                      SELECT date_trunc('month', r.created_at)::date, 'report', r.type FROM reports r WHERE r.company_id = %s""", cid)
                elif step == "vectors":
                    await ex(conn, "DELETE FROM retrieval_logs WHERE company_id=%s", cid)
                    await ex(conn, "DELETE FROM chunks WHERE company_id=%s", cid)
                    await ex(conn, "DELETE FROM parent_chunks WHERE company_id=%s", cid)
                elif step == "database":
                    for t in ("feedback", "reports", "messages", "conversations", "processing_jobs", "documents"):
                        await ex(conn, f"DELETE FROM {t} WHERE company_id=%s", cid)
                    # privacy: employee accounts (names, emails, password hashes) are deleted too.
                    # Company record + company admin accounts are kept so the admin can log in and re-upload.
                    await ex(conn, "DELETE FROM users WHERE company_id=%s AND role='employee'", cid)
                elif step == "files":
                    shutil.rmtree(company_dir(cid), ignore_errors=False) if company_dir(cid).exists() else None
                elif step == "temp_files":
                    shutil.rmtree(temp_dir(cid), ignore_errors=False) if temp_dir(cid).exists() else None
                elif step == "logs":
                    await ex(conn, "DELETE FROM error_logs WHERE company_id=%s", cid)
                steps[step] = "done"
                await ex(conn, "UPDATE deletion_jobs SET steps=%s WHERE id=%s", Jsonb(steps), job["id"])
        async with tx(bypass=True) as conn:
            await ex(conn, "UPDATE companies SET chatbot_state='not_started', kb_status='empty' WHERE id=%s", cid)
            await ex(conn, "UPDATE deletion_jobs SET status='completed', completed_at=now(), last_error=NULL WHERE id=%s", job["id"])
    except Exception as e:
        await log_error("deletion", type(e).__name__, f"deletion job {job['id']} failed", repr(e), cid)
        async with tx(bypass=True) as conn:
            await ex(conn, "UPDATE deletion_jobs SET status='failed', last_error=%s WHERE id=%s", repr(e)[:1000], job["id"])
    return True
