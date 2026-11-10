from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from psycopg.types.json import Jsonb

from ..db import ex, q, q1, tx
from ..deps import SA, SA_USER
from ..errors import err
from ..schemas import (AccessIn, CompanyCreate, CredentialIn, CredentialUpdate, EvalQuestionIn, EvalSettingsIn,
                       RagConfigUpdate, ReportStatusIn)
from ..security import create_token, encrypt_secret, hash_password
from ..services import analytics as an
from ..services.common import audit, recompute_kb_status
from ..services.config_service import COLUMNS, create_draft, get_active, live_validate, parse_config

router = APIRouter(prefix="/superadmin", tags=["SuperAdmin"])


async def requeue_for_model(conn, model: str) -> int:
    """Documents embedded with a different model must be re-processed, otherwise dense search would compare unrelated vectors."""
    rows = await q(conn, """UPDATE documents SET status='uploaded', error_message=NULL
                            WHERE status='ready' AND COALESCE(embedding_model,'') <> %s RETURNING id, company_id""", model)
    for r in rows:
        await ex(conn, "INSERT INTO processing_jobs (company_id, document_id) VALUES (%s,%s)", r["company_id"], r["id"])
    for cid in {r["company_id"] for r in rows}:
        await recompute_kb_status(conn, cid)
    return len(rows)


# ------------------------------ Global RAG configuration ------------------------------
@router.get("/rag-config", summary="Active global RAG configuration")
async def get_config(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return (await get_active(conn)).model_dump(mode="json")


@router.get("/rag-config/versions", summary="Configuration history")
async def config_versions(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, "SELECT id, version, status, validation_report, created_at, activated_at FROM rag_config_versions ORDER BY version DESC LIMIT 50")


@router.put("/rag-config", summary="Update config (validated before activation; last working config is kept on failure)")
async def update_config(body: RagConfigUpdate, user: dict = Depends(SA_USER)):
    async with tx(bypass=True) as conn:
        draft_id = await create_draft(conn, body, user["id"])
        row = await q1(conn, "SELECT * FROM rag_config_versions WHERE id=%s", draft_id)
    cfg = parse_config(row)
    report = {"ok": True, "skipped": True}
    if body.validate_live:
        async with tx(bypass=True) as conn:
            report = await live_validate(conn, cfg)
    async with tx(bypass=True) as conn:
        if not report["ok"]:
            await ex(conn, "UPDATE rag_config_versions SET status='failed', validation_report=%s WHERE id=%s", Jsonb(report), draft_id)
            await audit(conn, user["id"], "config.activation_failed", target_type="rag_config", target_id=draft_id, details={"report": report})
            active = await get_active(conn)
            raise err(422, "config_validation_failed",
                      f"The new configuration failed validation and was NOT activated. Version {active.version} remains active. Details: {report}")
        await ex(conn, "UPDATE rag_config_versions SET status='archived' WHERE status='active'")
        await ex(conn, "UPDATE rag_config_versions SET status='active', activated_at=now(), validation_report=%s WHERE id=%s", Jsonb(report), draft_id)
        await audit(conn, user["id"], "config.activate", target_type="rag_config", target_id=draft_id)
        new_cfg = await get_active(conn)
        requeued = await requeue_for_model(conn, new_cfg.embedding_cfg.model)
        return {"activated": True, "validation": report, "reprocessing_documents": requeued, "config": new_cfg.model_dump(mode="json")}


@router.post("/rag-config/{version_id}/rollback", summary="Re-activate an archived configuration version")
async def rollback_config(version_id: UUID, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    row = await q1(conn, "SELECT id, status FROM rag_config_versions WHERE id=%s", version_id)
    if not row or row["status"] not in ("archived",):
        raise err(404, "version_not_found", "Only archived versions can be rolled back to.")
    await ex(conn, "UPDATE rag_config_versions SET status='archived' WHERE status='active'")
    await ex(conn, "UPDATE rag_config_versions SET status='active', activated_at=now() WHERE id=%s", version_id)
    await audit(conn, user["id"], "config.rollback", target_type="rag_config", target_id=version_id)
    return {"ok": True, "reprocessing_documents": await requeue_for_model(conn, (await get_active(conn)).embedding_cfg.model)}


# ------------------------------ API credentials (keys never returned) ------------------------------
@router.get("/credentials", summary="List API credentials (masked)")
async def list_credentials(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, "SELECT id, provider, label, key_last4, is_active, created_at, updated_at FROM api_credentials ORDER BY created_at DESC")


@router.post("/credentials", status_code=201, summary="Add an API credential")
async def add_credential(body: CredentialIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    row = await q1(conn, """INSERT INTO api_credentials (provider, label, encrypted_key, key_last4, created_by)
                            VALUES (%s,%s,%s,%s,%s) RETURNING id, provider, label, key_last4, is_active, created_at""",
                   body.provider, body.label, encrypt_secret(body.api_key), body.api_key[-4:], user["id"])
    await audit(conn, user["id"], "credential.create", target_type="credential", target_id=row["id"], details={"label": body.label})
    return row


@router.patch("/credentials/{cred_id}", summary="Edit / replace / disable an API credential")
async def edit_credential(cred_id: UUID, body: CredentialUpdate, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    if not await q1(conn, "SELECT 1 FROM api_credentials WHERE id=%s", cred_id):
        raise err(404, "credential_not_found", "Credential not found.")
    if body.label is not None:
        await ex(conn, "UPDATE api_credentials SET label=%s WHERE id=%s", body.label, cred_id)
    if body.is_active is not None:
        await ex(conn, "UPDATE api_credentials SET is_active=%s WHERE id=%s", body.is_active, cred_id)
    if body.api_key is not None:
        await ex(conn, "UPDATE api_credentials SET encrypted_key=%s, key_last4=%s WHERE id=%s", encrypt_secret(body.api_key), body.api_key[-4:], cred_id)
    await audit(conn, user["id"], "credential.update", target_type="credential", target_id=cred_id,
                details={"key_replaced": body.api_key is not None})
    return await q1(conn, "SELECT id, provider, label, key_last4, is_active, updated_at FROM api_credentials WHERE id=%s", cred_id)


@router.delete("/credentials/{cred_id}", summary="Delete an API credential")
async def delete_credential(cred_id: UUID, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    active = await get_active(conn)
    if cred_id in (active.embedding_cfg.credential_id, active.llm_cfg.credential_id):
        raise err(409, "credential_in_use", "This credential is used by the active configuration. Switch the configuration first.")
    await ex(conn, "DELETE FROM api_credentials WHERE id=%s", cred_id)
    await audit(conn, user["id"], "credential.delete", target_type="credential", target_id=cred_id)
    return {"ok": True}


# ------------------------------ Companies ------------------------------
@router.get("/companies", summary="List companies with their admins")
async def list_companies(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, """SELECT c.id, c.name, c.access_status, c.chatbot_state, c.kb_status, c.created_at,
        a.full_name AS admin_name, a.email AS admin_email, a.phone AS admin_phone,
        (SELECT count(*) FROM users u WHERE u.company_id=c.id AND u.role='employee') AS employees,
        (SELECT count(*) FROM documents d WHERE d.company_id=c.id) AS documents
        FROM companies c LEFT JOIN LATERAL (SELECT * FROM users WHERE company_id=c.id AND role='company_admin' ORDER BY created_at LIMIT 1) a ON true
        WHERE NOT c.is_system ORDER BY c.created_at DESC""")


@router.post("/companies", status_code=201, summary="Register a company + its first admin")
async def create_company(body: CompanyCreate, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    c = await q1(conn, "INSERT INTO companies (name, created_by) VALUES (%s,%s) RETURNING id, name", body.company_name, user["id"])
    a = await q1(conn, """INSERT INTO users (company_id, role, full_name, email, phone, password_hash)
                          VALUES (%s,'company_admin',%s,%s,%s,%s) RETURNING id, full_name, email, phone""",
                 c["id"], body.admin_name, body.email, body.phone, hash_password(body.password))
    await audit(conn, user["id"], "company.create", company_id=c["id"], target_type="company", target_id=c["id"])
    return {"company": c, "admin": a}


@router.get("/companies/{company_id}", summary="Company details, admins and activity")
async def company_detail(company_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    c = await q1(conn, "SELECT * FROM companies WHERE id=%s", company_id)
    if not c:
        raise err(404, "company_not_found", "Company not found.")
    admins = await q(conn, "SELECT id, full_name, email, phone, status, last_login_at FROM users WHERE company_id=%s AND role='company_admin'", company_id)
    employees = await q1(conn, "SELECT count(*) AS total, count(*) FILTER (WHERE status='active') AS active FROM users WHERE company_id=%s AND role='employee'", company_id)
    deletion = await q1(conn, "SELECT id, status, steps, attempts, last_error, created_at, completed_at FROM deletion_jobs WHERE company_id=%s ORDER BY created_at DESC LIMIT 1", company_id)
    activity = await q(conn, "SELECT action, actor_id, created_at FROM audit_logs WHERE company_id=%s ORDER BY created_at DESC LIMIT 20", company_id)
    return {"company": c, "admins": admins, "employees": employees, "latest_deletion": deletion,
            "recent_activity": activity, "analytics": await an.overview(conn, company_id)}


@router.patch("/companies/{company_id}/access", summary="Activate / deactivate a company's access")
async def set_access(company_id: UUID, body: AccessIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    row = await q1(conn, "UPDATE companies SET access_status=%s WHERE id=%s RETURNING id, name, access_status",
                   "active" if body.active else "inactive", company_id)
    if not row:
        raise err(404, "company_not_found", "Company not found.")
    await audit(conn, user["id"], "company.activate" if body.active else "company.deactivate", company_id=company_id, target_type="company", target_id=company_id)
    return row


@router.post("/companies/{company_id}/impersonate", summary="Enter as the company admin (short-lived, audited)")
async def impersonate(company_id: UUID, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    admin = await q1(conn, "SELECT id, role, company_id, full_name FROM users WHERE company_id=%s AND role='company_admin' AND status='active' ORDER BY created_at LIMIT 1", company_id)
    if not admin:
        raise err(404, "admin_not_found", "This company has no active administrator.")
    await audit(conn, user["id"], "company.impersonate", company_id=company_id, target_type="user", target_id=admin["id"])
    return {"access_token": create_token(admin["id"], admin["role"], company_id, impersonator=user["id"], minutes=60),
            "token_type": "bearer", "expires_in_minutes": 60, "admin_name": admin["full_name"]}


# ------------------------------ Evaluation settings ------------------------------
@router.get("/evaluation/settings")
async def get_eval_settings(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q1(conn, "SELECT every_n_answers, enabled, updated_at FROM evaluation_settings WHERE id=1")


@router.put("/evaluation/settings", summary="When to ask employees for feedback")
async def set_eval_settings(body: EvalSettingsIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    await ex(conn, "UPDATE evaluation_settings SET every_n_answers=%s, enabled=%s, updated_by=%s, updated_at=now() WHERE id=1", body.every_n_answers, body.enabled, user["id"])
    await audit(conn, user["id"], "evaluation.settings", details=body.model_dump())
    return body


@router.get("/evaluation/questions")
async def list_eval_questions(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, "SELECT * FROM evaluation_questions ORDER BY position, created_at")


@router.post("/evaluation/questions", status_code=201)
async def add_eval_question(body: EvalQuestionIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    row = await q1(conn, "INSERT INTO evaluation_questions (text, type, position, is_active) VALUES (%s,%s,%s,%s) RETURNING *", body.text, body.type, body.position, body.is_active)
    await audit(conn, user["id"], "evaluation.question.create", target_id=row["id"])
    return row


@router.put("/evaluation/questions/{qid}")
async def edit_eval_question(qid: UUID, body: EvalQuestionIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    row = await q1(conn, "UPDATE evaluation_questions SET text=%s, type=%s, position=%s, is_active=%s WHERE id=%s RETURNING *", body.text, body.type, body.position, body.is_active, qid)
    if not row:
        raise err(404, "question_not_found", "Evaluation question not found.")
    return row


@router.delete("/evaluation/questions/{qid}")
async def delete_eval_question(qid: UUID, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    await ex(conn, "DELETE FROM evaluation_questions WHERE id=%s", qid)      # cascades its collected answers
    await audit(conn, user["id"], "evaluation.question.delete", target_id=qid)
    return {"ok": True}


# ------------------------------ Analytics & reports ------------------------------
@router.get("/analytics", summary="Platform-wide analytics (or one company via ?company_id=)")
async def analytics(company_id: Optional[UUID] = None, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    out = {"overview": await an.overview(conn, company_id), "top_questions": await an.questions_report(conn, company_id, 20)}
    if not company_id:
        out["companies"] = await an.per_company(conn)
    return out


@router.get("/analytics/feedback", summary="Feedback trends / entries")
async def feedback(company_id: Optional[UUID] = None, limit: int = Query(50, le=500), offset: int = 0, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await an.feedback_list(conn, company_id, limit, offset)


@router.get("/reports", summary="Reported cases (per company with ?company_id=)")
async def reports(company_id: Optional[UUID] = None, status: Optional[str] = None, limit: int = Query(50, le=500), offset: int = 0, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await an.reports_list(conn, company_id, status, limit, offset)


@router.patch("/reports/{report_id}", summary="Update a reported case's status")
async def update_report(report_id: UUID, body: ReportStatusIn, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    row = await q1(conn, "UPDATE reports SET status=%s WHERE id=%s RETURNING id, status", body.status, report_id)
    if not row:
        raise err(404, "report_not_found", "Report not found.")
    return row


@router.get("/audit-logs", summary="Administrative audit trail")
async def audit_logs(company_id: Optional[UUID] = None, limit: int = Query(100, le=500), ctx=Depends(SA, scope="function")):
    _, conn = ctx
    if company_id:
        return await q(conn, "SELECT * FROM audit_logs WHERE company_id=%s ORDER BY created_at DESC LIMIT %s", company_id, limit)
    return await q(conn, "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT %s", limit)
