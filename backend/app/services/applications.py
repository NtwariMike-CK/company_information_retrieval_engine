from ..db import ex, q, q1
from ..errors import err


async def get_fields(conn, only_active: bool = True):
    return await q(conn, f"SELECT * FROM application_form_fields {'WHERE is_active' if only_active else ''} ORDER BY position, created_at")


def validate_answers(fields: list[dict], answers: dict, partial: bool = False):
    """Validate against the form definition stored in the database. Returns (clean_answers, errors)."""
    clean, errors = {}, {}
    for f in fields:
        k, label = f["key"], f["label"]
        if k not in answers:
            if f["required"] and not partial:
                errors[k] = f"{label} is required"
            continue
        v = answers[k]
        empty = v is None or v == "" or v == []
        if empty:
            if f["required"]:
                errors[k] = f"{label} is required"
            continue
        t = f["type"]
        try:
            if t in ("text", "textarea"):
                v = str(v).strip()
                if len(v) > (3000 if t == "textarea" else 300):
                    raise ValueError("is too long")
            elif t == "number":
                v = float(v)
                if v < 0 or v > 10_000_000:
                    raise ValueError("must be a positive number")
                v = int(v) if v == int(v) else v
            elif t == "select":
                if v not in f["options"]:
                    raise ValueError("is not a valid choice")
            elif t == "multiselect":
                if not isinstance(v, list) or not v or any(x not in f["options"] for x in v):
                    raise ValueError("contains an invalid choice")
        except (ValueError, TypeError) as e:
            errors[k] = f"{label} {e}" if isinstance(e, ValueError) and str(e) else f"{label} is invalid"
            continue
        clean[k] = v
    return clean, errors


def raise_if_invalid(errors: dict):
    if errors:
        from fastapi import HTTPException
        raise HTTPException(422, detail={"code": "validation_failed", "message": "Please fix: " + "; ".join(errors.values()), "fields": errors})


async def add_message(conn, application_id, sender_id, sender_role, kind, body, status_to=None):
    await ex(conn, """INSERT INTO application_messages (application_id, sender_id, sender_role, kind, body, status_to)
                      VALUES (%s,%s,%s,%s,%s,%s)""", application_id, sender_id, sender_role, kind, body, status_to)


async def thread(conn, application_id):
    return await q(conn, """SELECT m.id, m.kind, m.sender_role, m.body, m.status_to, m.created_at, u.full_name AS sender_name
                            FROM application_messages m LEFT JOIN users u ON u.id = m.sender_id
                            WHERE m.application_id = %s ORDER BY m.created_at, m.id""", application_id)


async def application_detail(conn, application_id):
    app = await q1(conn, "SELECT * FROM company_applications WHERE id=%s", application_id)
    if not app:
        raise err(404, "application_not_found", "Request not found.")
    app["messages"] = await thread(conn, application_id)
    return app


CURRENT_STEPS_SQL = """SELECT s.id AS step_id, s.key, s.position, s.requires_acceptance, v.id AS version_id, v.version, v.title, v.body_markdown
                       FROM onboarding_steps s JOIN onboarding_step_versions v ON v.id = s.current_version_id
                       WHERE s.is_active ORDER BY s.position, s.created_at"""
