from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ..db import ex, q, q1
from ..deps import tenant
from ..errors import err
from ..schemas import ApplicationIn, ApplicationRespondIn, CompleteOnboardingIn
from ..services.applications import (CURRENT_STEPS_SQL, add_message, application_detail, get_fields, raise_if_invalid,
                                     thread, validate_answers)
from ..services.common import audit
from ..services.mailer import link, notify_superadmins, queue_email

router = APIRouter(prefix="/apply", tags=["Company Request (Applicant)"])
APPL = tenant("applicant")
OPEN = ("pending", "needs_info", "approved")


@router.get("/form", summary="The request form (defined in the database)")
async def form(ctx=Depends(APPL, scope="function")):
    _, conn = ctx
    rows = await get_fields(conn)
    return [{k: r[k] for k in ("key", "label", "help_text", "type", "options", "required", "position")} for r in rows]


@router.get("/state", summary="My requests: current status, conversation with the reviewer, history")
async def state(ctx=Depends(APPL, scope="function")):
    user, conn = ctx
    apps = await q(conn, """SELECT id, status, company_name, submitted_at, updated_at, decision_comment
                            FROM company_applications WHERE applicant_id=%s ORDER BY submitted_at DESC""", user["id"])
    current = await application_detail(conn, apps[0]["id"]) if apps else None
    return {"applications": apps, "current": current, "can_submit": not apps or apps[0]["status"] == "rejected"}


@router.post("/applications", status_code=201, summary="Submit a company request (one open request at a time)")
async def submit(body: ApplicationIn, ctx=Depends(APPL, scope="function")):
    user, conn = ctx
    if await q1(conn, "SELECT 1 FROM company_applications WHERE applicant_id=%s AND status = ANY(%s)", user["id"], list(OPEN)):
        raise err(409, "open_application_exists", "You already have an open request. Wait for the review or respond to it.")
    if body.resubmission_of and not await q1(conn, "SELECT 1 FROM company_applications WHERE id=%s AND applicant_id=%s AND status='rejected'",
                                             body.resubmission_of, user["id"]):
        raise err(404, "application_not_found", "The rejected request to resubmit was not found.")
    fields = await get_fields(conn)
    clean, errors = validate_answers(fields, body.answers)
    raise_if_invalid(errors)
    app = await q1(conn, """INSERT INTO company_applications (applicant_id, company_name, answers, resubmission_of)
                            VALUES (%s,%s,%s::jsonb,%s) RETURNING id""",
                   user["id"], clean["company_name"], __import__("json").dumps(clean), body.resubmission_of)
    await add_message(conn, app["id"], user["id"], "applicant", "submission", "Request submitted.", "pending")
    await queue_email(conn, user["email"], "We received your company request",
                      f"Hello {user['full_name']},\n\nWe received the request for \"{clean['company_name']}\". Our team will review it and reply in the portal "
                      f"(and by email): {link('/apply')}\n\nThank you.", app["id"])
    await notify_superadmins(conn, f"New company request: {clean['company_name']}",
                             f"{user['full_name']} ({user['email']}) submitted a request for \"{clean['company_name']}\".\nReview it: {link('/superadmin/applications/' + str(app['id']))}", app["id"])
    await audit(conn, user["id"], "application.submit", target_type="application", target_id=app["id"])
    return await application_detail(conn, app["id"])


@router.post("/applications/{app_id}/respond", summary="Answer the reviewer's request for more information")
async def respond(app_id: UUID, body: ApplicationRespondIn, ctx=Depends(APPL, scope="function")):
    user, conn = ctx
    app = await q1(conn, "SELECT * FROM company_applications WHERE id=%s AND applicant_id=%s FOR UPDATE", app_id, user["id"])
    if not app:
        raise err(404, "application_not_found", "Request not found.")
    if app["status"] != "needs_info":
        raise err(409, "not_waiting", "This request is not waiting for more information.")
    if body.answers is not None:
        fields = await get_fields(conn)
        clean, errors = validate_answers(fields, {**app["answers"], **body.answers})
        raise_if_invalid(errors)
        await ex(conn, "UPDATE company_applications SET answers=%s::jsonb, company_name=%s WHERE id=%s",
                 __import__("json").dumps(clean), clean["company_name"], app_id)
    await add_message(conn, app_id, user["id"], "applicant", "response", body.message, "pending")
    await ex(conn, "UPDATE company_applications SET status='pending' WHERE id=%s", app_id)
    await notify_superadmins(conn, f"Applicant responded: {app['company_name']}",
                             f"{user['full_name']} replied to your request for more information.\n{link('/superadmin/applications/' + str(app_id))}", app_id)
    return await application_detail(conn, app_id)


@router.get("/applications/{app_id}", summary="One of my requests with its conversation")
async def detail(app_id: UUID, ctx=Depends(APPL, scope="function")):
    user, conn = ctx
    if not await q1(conn, "SELECT 1 FROM company_applications WHERE id=%s AND applicant_id=%s", app_id, user["id"]):
        raise err(404, "application_not_found", "Request not found.")
    return await application_detail(conn, app_id)


async def _approved(conn, user):
    app = await q1(conn, "SELECT * FROM company_applications WHERE applicant_id=%s AND status='approved' FOR UPDATE", user["id"])
    if not app:
        raise err(403, "not_approved", "Your request has not been approved yet.")
    return app


@router.get("/onboarding", summary="Walkthrough pages for an approved request")
async def onboarding(ctx=Depends(APPL, scope="function")):
    user, conn = ctx
    await _approved(conn, user)
    return await q(conn, CURRENT_STEPS_SQL)


@router.post("/onboarding/complete", summary="Accept the terms: creates the company and makes you its admin")
async def complete(body: CompleteOnboardingIn, request: Request, ctx=Depends(APPL, scope="function")):
    user, conn = ctx
    app = await _approved(conn, user)
    steps = await q(conn, CURRENT_STEPS_SQL)
    accepted = {a.step_id: a.version_id for a in body.accepted}
    for s in steps:
        if s["requires_acceptance"] and accepted.get(s["step_id"]) != s["version_id"]:
            raise err(422, "must_accept", f"You must accept the latest version of \"{s['title']}\" to continue. Please reload the page.")
    if await q1(conn, "SELECT 1 FROM companies WHERE lower(name)=lower(%s)", app["company_name"]):
        raise err(409, "company_name_taken", "A company with this name already exists. Please contact the platform team.")
    company = await q1(conn, "INSERT INTO companies (name, created_by) VALUES (%s,%s) RETURNING id, name", app["company_name"], app["reviewed_by"])
    await ex(conn, "UPDATE users SET role='company_admin', company_id=%s WHERE id=%s", company["id"], user["id"])
    ip = request.client.host if request.client else None
    for s in steps:
        if accepted.get(s["step_id"]) == s["version_id"]:
            await ex(conn, """INSERT INTO terms_acceptances (user_id, company_id, application_id, step_version_id, ip_address, user_agent)
                              VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (user_id, step_version_id) DO NOTHING""",
                     user["id"], company["id"], app["id"], s["version_id"], ip, request.headers.get("user-agent", "")[:300])
    await ex(conn, "UPDATE company_applications SET status='onboarded', company_id=%s, onboarded_at=now() WHERE id=%s", company["id"], app["id"])
    await add_message(conn, app["id"], user["id"], "applicant", "status", "Terms accepted. Company workspace created.", "onboarded")
    await audit(conn, user["id"], "application.onboarded", company_id=company["id"], target_type="application", target_id=app["id"])
    await notify_superadmins(conn, f"Company onboarded: {company['name']}", f"{user['full_name']} accepted the terms. The workspace for \"{company['name']}\" is ready.", app["id"])
    return {"company": company, "next": "/admin"}
