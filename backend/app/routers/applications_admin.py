from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends

from ..db import ex, q, q1
from ..deps import SA
from ..errors import err
from ..schemas import CommentIn, DecisionIn
from ..services.applications import add_message, application_detail, get_fields
from ..services.common import audit
from ..services.mailer import link, queue_email

router = APIRouter(prefix="/superadmin/applications", tags=["SuperAdmin - Company Requests"])


@router.get("", summary="Company requests (filter by status)")
async def list_applications(status: Optional[str] = None, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    where, args = ("WHERE a.status = %s", (status,)) if status else ("", ())
    return await q(conn, f"""SELECT a.id, a.status, a.company_name, a.submitted_at, a.updated_at, a.resubmission_of IS NOT NULL AS is_resubmission,
                             u.full_name AS applicant_name, u.email AS applicant_email, u.phone AS applicant_phone,
                             (SELECT max(created_at) FROM application_messages m WHERE m.application_id = a.id) AS last_activity
                             FROM company_applications a JOIN users u ON u.id = a.applicant_id {where}
                             ORDER BY (a.status = 'pending') DESC, a.updated_at DESC""", *args)


@router.get("/summary", summary="Counts per status (for the sidebar badge)")
async def summary(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    rows = await q(conn, "SELECT status, count(*) AS n FROM company_applications GROUP BY status")
    return {r["status"]: r["n"] for r in rows}


@router.get("/{app_id}", summary="Request details, answers and conversation")
async def detail(app_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    app = await application_detail(conn, app_id)
    applicant = await q1(conn, "SELECT id, full_name, email, phone, created_at FROM users WHERE id=%s", app["applicant_id"])
    return {**app, "applicant": applicant, "fields": await get_fields(conn, only_active=False)}


@router.post("/{app_id}/decision", summary="Approve, reject (comment required) or request more information (comment required)")
async def decide(app_id: UUID, body: DecisionIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    app = await q1(conn, "SELECT a.*, u.email AS applicant_email, u.full_name AS applicant_name FROM company_applications a JOIN users u ON u.id=a.applicant_id WHERE a.id=%s FOR UPDATE", app_id)
    if not app:
        raise err(404, "application_not_found", "Request not found.")
    comment = body.comment.strip()
    allowed = {"approve": ("pending", "needs_info"), "reject": ("pending", "needs_info", "approved"), "request_info": ("pending", "needs_info")}
    if app["status"] not in allowed[body.action]:
        raise err(409, "invalid_transition", f"A request that is \"{app['status']}\" cannot be {body.action.replace('_', ' ')}d.")
    if body.action in ("reject", "request_info") and len(comment) < 3:
        raise err(422, "comment_required", "Please write a comment for the applicant.")
    if body.action == "approve" and await q1(conn, "SELECT 1 FROM companies WHERE lower(name)=lower(%s)", app["company_name"]):
        raise err(409, "company_name_taken", "A company with this name already exists. Request more information or reject.")
    new_status, kind = {"approve": ("approved", "approval"), "reject": ("rejected", "rejection"), "request_info": ("needs_info", "info_request")}[body.action]
    await ex(conn, "UPDATE company_applications SET status=%s, decision_comment=%s, reviewed_by=%s, reviewed_at=now() WHERE id=%s",
             new_status, comment or None, user["id"], app_id)
    await add_message(conn, app_id, user["id"], "super_admin", kind, comment or "Your request was approved.", new_status)
    subject, text = {
        "approve": ("Your company request was approved", f"Good news! The request for \"{app['company_name']}\" was approved.\nSign in to complete the short onboarding and open your workspace: {link('/apply')}"),
        "reject": ("Update on your company request", f"Your request for \"{app['company_name']}\" was not approved.\n\nReviewer comment:\n{comment}\n\nYou can review the comment and submit a new request: {link('/apply')}"),
        "request_info": ("More information needed for your company request", f"We need a little more information about \"{app['company_name']}\":\n\n{comment}\n\nPlease reply in the portal: {link('/apply')}"),
    }[body.action]
    await queue_email(conn, app["applicant_email"], subject, f"Hello {app['applicant_name']},\n\n{text}\n", app_id)
    await audit(conn, user["id"], f"application.{body.action}", target_type="application", target_id=app_id)
    return await application_detail(conn, app_id)


@router.post("/{app_id}/messages", summary="Send a comment to the applicant without changing the status")
async def comment(app_id: UUID, body: CommentIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    app = await q1(conn, "SELECT a.company_name, u.email, u.full_name FROM company_applications a JOIN users u ON u.id=a.applicant_id WHERE a.id=%s", app_id)
    if not app:
        raise err(404, "application_not_found", "Request not found.")
    await add_message(conn, app_id, user["id"], "super_admin", "comment", body.body.strip())
    await queue_email(conn, app["email"], f"New message about \"{app['company_name']}\"", f"Hello {app['full_name']},\n\n{body.body.strip()}\n\nReply in the portal: {link('/apply')}\n", app_id)
    return await application_detail(conn, app_id)
