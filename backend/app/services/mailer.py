"""Email outbox. Messages are queued in the database; the worker sends them over SMTP when SMTP_HOST is set,
otherwise they are marked 'skipped' (the portal thread is always the source of truth)."""
import asyncio, logging, smtplib
from email.message import EmailMessage

from ..db import ex, q, tx
from ..settings import settings

log = logging.getLogger("mailer")


async def queue_email(conn, to_email: str, subject: str, body: str, application_id=None):
    await ex(conn, "INSERT INTO email_outbox (to_email, subject, body, application_id) VALUES (%s,%s,%s,%s)",
             to_email, subject[:300], body, application_id)


async def notify_superadmins(conn, subject: str, body: str, application_id=None):
    rows = await q(conn, "SELECT email FROM users WHERE role='super_admin' AND status='active'")
    emails = {r["email"] for r in rows}
    if settings.notify_email:
        emails.add(settings.notify_email)
    for e in emails:
        await queue_email(conn, e, subject, body, application_id)


def _smtp_send(row: dict):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, row["to_email"], row["subject"]
    msg.set_content(row["body"])
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        if settings.smtp_tls:
            s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def send_pending(limit: int = 10) -> bool:
    async with tx(bypass=True) as conn:
        rows = await q(conn, """UPDATE email_outbox SET attempts = attempts + 1 WHERE id IN
                                (SELECT id FROM email_outbox WHERE status = 'pending' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT %s)
                                RETURNING *""", limit)
    for r in rows:
        status, err_text = "sent", None
        if not settings.smtp_host:
            status, err_text = "skipped", "SMTP not configured"
        else:
            try:
                await asyncio.to_thread(_smtp_send, r)
            except Exception as e:
                status, err_text = ("failed" if r["attempts"] >= 3 else "pending"), repr(e)[:500]
                log.warning("email %s failed: %s", r["id"], e)
        async with tx(bypass=True) as conn:
            await ex(conn, "UPDATE email_outbox SET status=%s, last_error=%s, sent_at = CASE WHEN %s = 'sent' THEN now() END WHERE id=%s",
                     status, err_text, status, r["id"])
    return bool(rows)


def link(path: str) -> str:
    return settings.frontend_url.rstrip("/") + path
