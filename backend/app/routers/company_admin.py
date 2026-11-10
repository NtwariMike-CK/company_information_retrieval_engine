import hashlib, json, re, shutil, tempfile, uuid, zipfile
from pathlib import Path
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from psycopg.types.json import Jsonb

from ..db import ex, q, q1
from ..deps import CA
from ..errors import err
from ..schemas import EmployeeCreate, EmployeeUpdate, ExportIn, ReportStatusIn, ServiceEndIn
from ..security import hash_password
from ..services import analytics as an
from ..services.common import audit, recompute_kb_status
from ..services.config_service import get_active
from ..services.deletion import company_dir, temp_dir
from ..settings import settings

router = APIRouter(prefix="/company", tags=["Company Admin"])


# ------------------------------ Employees ------------------------------
@router.get("/employees", summary="List employees")
async def list_employees(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    return await q(conn, "SELECT id, full_name, email, role, status, last_login_at, created_at FROM users WHERE company_id=%s ORDER BY created_at DESC", user["company_id"])


@router.post("/employees", status_code=201, summary="Create an employee account in this company")
async def create_employee(body: EmployeeCreate, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    row = await q1(conn, """INSERT INTO users (company_id, role, full_name, email, password_hash, status)
                            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, full_name, email, role, status""",
                   user["company_id"], body.role, body.full_name, body.email, hash_password(body.password), body.status)
    await audit(conn, user["id"], "employee.create", company_id=user["company_id"], target_type="user", target_id=row["id"])
    return row


@router.patch("/employees/{employee_id}", summary="Edit / activate / deactivate an employee")
async def update_employee(employee_id: UUID, body: EmployeeUpdate, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    target = await q1(conn, "SELECT id FROM users WHERE id=%s AND company_id=%s", employee_id, user["company_id"])
    if not target:
        raise err(404, "employee_not_found", "Employee not found.")
    if employee_id == user["id"] and (body.status == "inactive" or (body.role and body.role != "company_admin")):
        raise err(400, "cannot_modify_self", "You cannot deactivate or demote your own account.")
    for col, val in (("full_name", body.full_name), ("role", body.role), ("status", body.status)):
        if val is not None:
            await ex(conn, f"UPDATE users SET {col}=%s WHERE id=%s", val, employee_id)
    if body.password:
        await ex(conn, "UPDATE users SET password_hash=%s WHERE id=%s", hash_password(body.password), employee_id)
    await audit(conn, user["id"], "employee.update", company_id=user["company_id"], target_type="user", target_id=employee_id,
                details={"fields": [k for k, v in body.model_dump().items() if v is not None and k != "password"], "password_reset": bool(body.password)})
    return await q1(conn, "SELECT id, full_name, email, role, status FROM users WHERE id=%s", employee_id)


# ------------------------------ Knowledge base ------------------------------
@router.get("/documents", summary="Documents with live pipeline progress")
async def list_documents(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    return await q(conn, """SELECT d.id, d.filename, d.file_type, d.size_bytes, d.status, d.error_message, d.created_at,
        j.id AS job_id, j.stage, j.status AS job_status, j.progress_pct, j.error_message AS job_error, j.eda_stats,
        (SELECT count(*) FROM chunks c WHERE c.document_id=d.id) AS chunks
        FROM documents d LEFT JOIN LATERAL (SELECT * FROM processing_jobs WHERE document_id=d.id ORDER BY created_at DESC LIMIT 1) j ON true
        WHERE d.company_id=%s ORDER BY d.created_at DESC""", user["company_id"])


@router.post("/documents", status_code=202, summary="Upload one or more documents (processed in the background)")
async def upload_documents(files: list[UploadFile] = File(...), ctx=Depends(CA, scope="function")):
    user, conn = ctx
    cid = user["company_id"]
    company = await q1(conn, "SELECT chatbot_state FROM companies WHERE id=%s", cid)
    if company["chatbot_state"] == "ended":
        raise err(409, "service_ended", "Service data is being deleted. Please wait until deletion completes before uploading.")
    cfg = (await get_active(conn)).document_cfg
    count = (await q1(conn, "SELECT count(*) AS n FROM documents WHERE company_id=%s", cid))["n"]
    tmp = temp_dir(cid)
    tmp.mkdir(parents=True, exist_ok=True)
    results = []
    for f in files:
        name = Path(f.filename or "file").name
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in cfg.allowed_types:
            results.append({"filename": name, "status": "rejected", "reason": f"File type .{ext} is not allowed. Allowed: {', '.join(cfg.allowed_types)}"})
            continue
        if count >= cfg.max_files:
            results.append({"filename": name, "status": "rejected", "reason": f"Document limit reached ({cfg.max_files})."})
            continue
        tmp_path, size, h = tmp / f"{uuid.uuid4()}.part", 0, hashlib.sha256()
        too_big = False
        with open(tmp_path, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > cfg.max_file_mb * 1024 * 1024:
                    too_big = True
                    break
                h.update(chunk)
                out.write(chunk)
        if too_big or size == 0:
            tmp_path.unlink(missing_ok=True)
            results.append({"filename": name, "status": "rejected", "reason": f"File exceeds {cfg.max_file_mb} MB." if too_big else "File is empty."})
            continue
        digest = h.hexdigest()
        if await q1(conn, "SELECT 1 FROM documents WHERE company_id=%s AND content_hash=%s", cid, digest):
            tmp_path.unlink(missing_ok=True)
            results.append({"filename": name, "status": "duplicate", "reason": "This exact file was already uploaded."})
            continue
        doc_id = uuid.uuid4()
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        dest = company_dir(cid) / str(doc_id) / safe
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_path), dest)
        await ex(conn, """INSERT INTO documents (id, company_id, uploaded_by, filename, file_type, size_bytes, storage_path, content_hash, status)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'uploaded')""", doc_id, cid, user["id"], name, ext, size, str(dest), digest)
        job = await q1(conn, "INSERT INTO processing_jobs (company_id, document_id) VALUES (%s,%s) RETURNING id", cid, doc_id)
        count += 1
        results.append({"filename": name, "status": "queued", "document_id": doc_id, "job_id": job["id"]})
    await recompute_kb_status(conn, cid)
    await audit(conn, user["id"], "documents.upload", company_id=cid, details={"files": len(files), "queued": sum(r["status"] == "queued" for r in results)})
    return {"results": results}


@router.delete("/documents/{doc_id}", summary="Delete a document and its chunks/embeddings")
async def delete_document(doc_id: UUID, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    cid = user["company_id"]
    doc = await q1(conn, "SELECT id, storage_path, status FROM documents WHERE id=%s AND company_id=%s", doc_id, cid)
    if not doc:
        raise err(404, "document_not_found", "Document not found.")
    if doc["status"] == "processing":
        raise err(409, "document_processing", "This document is being processed. Try again when it finishes.")
    await ex(conn, "DELETE FROM retrieval_logs WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=%s)", doc_id)
    await ex(conn, "DELETE FROM documents WHERE id=%s", doc_id)    # cascades parent_chunks, chunks, jobs
    shutil.rmtree(Path(doc["storage_path"]).parent, ignore_errors=True)
    await recompute_kb_status(conn, cid)
    await audit(conn, user["id"], "document.delete", company_id=cid, target_type="document", target_id=doc_id)
    return {"ok": True}


@router.post("/documents/{doc_id}/retry", summary="Retry a failed document")
async def retry_document(doc_id: UUID, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    cid = user["company_id"]
    doc = await q1(conn, "SELECT status FROM documents WHERE id=%s AND company_id=%s", doc_id, cid)
    if not doc:
        raise err(404, "document_not_found", "Document not found.")
    if doc["status"] != "failed":
        raise err(409, "not_failed", "Only failed documents can be retried.")
    await ex(conn, "UPDATE documents SET status='uploaded', error_message=NULL WHERE id=%s", doc_id)
    await ex(conn, "INSERT INTO processing_jobs (company_id, document_id) VALUES (%s,%s)", cid, doc_id)
    await recompute_kb_status(conn, cid)
    return {"ok": True}


@router.get("/knowledge-base", summary="Knowledge-base readiness (green = ready)")
async def knowledge_base(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    c = await q1(conn, "SELECT chatbot_state, kb_status FROM companies WHERE id=%s", user["company_id"])
    counts = await q(conn, "SELECT status, count(*) AS n FROM documents WHERE company_id=%s GROUP BY status", user["company_id"])
    return {**c, "documents_by_status": counts, "ready": c["kb_status"] == "ready",
            "can_start": c["kb_status"] == "ready" and c["chatbot_state"] in ("not_started", "paused")}


# ------------------------------ Start / Pause / End ------------------------------
@router.post("/service/start", summary="Start (or resume) chatbot usage")
async def start_service(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    c = await q1(conn, "SELECT chatbot_state, kb_status FROM companies WHERE id=%s FOR UPDATE", user["company_id"])
    if c["chatbot_state"] == "ended":
        raise err(409, "service_ended", "Service has ended. Upload and process documents again first.")
    if c["kb_status"] != "ready":
        raise err(409, "kb_not_ready", "The knowledge base is not ready yet.")
    await ex(conn, "UPDATE companies SET chatbot_state='started' WHERE id=%s", user["company_id"])
    await audit(conn, user["id"], "service.start", company_id=user["company_id"])
    return {"chatbot_state": "started"}


@router.post("/service/pause", summary="Pause chatbot usage (all data is preserved)")
async def pause_service(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    c = await q1(conn, "SELECT chatbot_state FROM companies WHERE id=%s", user["company_id"])
    if c["chatbot_state"] != "started":
        raise err(409, "not_started", "The chatbot is not currently started.")
    await ex(conn, "UPDATE companies SET chatbot_state='paused' WHERE id=%s", user["company_id"])
    await audit(conn, user["id"], "service.pause", company_id=user["company_id"])
    return {"chatbot_state": "paused"}


@router.post("/service/end", summary="END service: permanently delete ALL company data")
async def end_service(body: ServiceEndIn, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    cid = user["company_id"]
    c = await q1(conn, "SELECT name, chatbot_state FROM companies WHERE id=%s FOR UPDATE", cid)
    if c["chatbot_state"] == "ended":
        raise err(409, "already_ending", "Deletion is already in progress.")
    await ex(conn, "UPDATE companies SET chatbot_state='ended' WHERE id=%s", cid)
    job = await q1(conn, "INSERT INTO deletion_jobs (company_id, company_name, requested_by) VALUES (%s,%s,%s) RETURNING id", cid, c["name"], user["id"])
    await audit(conn, user["id"], "service.end", company_id=cid, target_type="deletion_job", target_id=job["id"])
    return {"chatbot_state": "ended", "deletion_job_id": job["id"], "message": "Deletion started. Track progress at GET /company/service/deletion."}


@router.get("/service/deletion", summary="Deletion progress")
async def deletion_status(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    return await q1(conn, "SELECT id, status, steps, attempts, last_error, created_at, completed_at FROM deletion_jobs WHERE company_id=%s ORDER BY created_at DESC LIMIT 1", user["company_id"])


# ------------------------------ Analytics ------------------------------
def _file(content: str, name: str, media: str):
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/analytics/overview", summary="Company overview metrics")
async def overview(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    return await an.overview(conn, user["company_id"])


@router.get("/analytics/feedback", summary="Employee feedback with question + RAG response")
async def feedback(limit: int = Query(50, le=500), offset: int = 0, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    return await an.feedback_list(conn, user["company_id"], limit, offset)


@router.get("/analytics/reports", summary="Reported cases")
async def reports(status: Optional[str] = None, limit: int = Query(50, le=500), offset: int = 0, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    return await an.reports_list(conn, user["company_id"], status, limit, offset)


@router.patch("/reports/{report_id}", summary="Update a reported case's status")
async def update_report(report_id: UUID, body: ReportStatusIn, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    row = await q1(conn, "UPDATE reports SET status=%s WHERE id=%s AND company_id=%s RETURNING id, status", body.status, report_id, user["company_id"])
    if not row:
        raise err(404, "report_not_found", "Report not found.")
    return row


@router.get("/analytics/questions", summary="Questions asked: count + whether information was present")
async def questions(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    return await an.questions_report(conn, user["company_id"])


@router.get("/analytics/questions/export", summary="Download questions report (CSV)")
async def questions_export(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    rows = await an.questions_report(conn, user["company_id"], 10000)
    return _file(an.to_csv(rows, ["question", "times_asked", "found_info", "not_found", "information_present", "last_asked"]), "questions_report.csv", "text/csv")


@router.get("/conversations", summary="Employee conversations")
async def conversations(limit: int = Query(50, le=500), offset: int = 0, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    return await an.conversations_list(conn, user["company_id"], limit, offset)


@router.get("/conversations/{conv_id}", summary="One conversation with answers, feedback and retrieval evidence")
async def conversation(conv_id: UUID, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    d = await an.conversation_detail(conn, conv_id, user["company_id"])
    if not d:
        raise err(404, "conversation_not_found", "Conversation not found.")
    return d


@router.post("/conversations/export", summary="Download selected (or all) conversations as CSV/JSON")
async def conversations_export(body: ExportIn, ctx=Depends(CA, scope="function")):
    user, conn = ctx
    rows = await an.conversation_export_rows(conn, user["company_id"], body.conversation_ids)
    if body.format == "json":
        return _file(json.dumps(rows, default=str, indent=2), "conversations.json", "application/json")
    return _file(an.to_csv(rows, an.EXPORT_COLUMNS), "conversations.csv", "text/csv")


# ------------------------------ Company request & data export ------------------------------
@router.get("/request", summary="The request I submitted, its history and the terms I accepted")
async def my_request(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    app = await q1(conn, "SELECT * FROM company_applications WHERE applicant_id=%s AND status='onboarded' ORDER BY submitted_at DESC LIMIT 1", user["id"])
    if not app:
        return {"application": None}
    from ..services.applications import get_fields, thread
    accepted = await q(conn, """SELECT s.key, v.title, v.version, v.body_markdown, t.accepted_at
                                FROM terms_acceptances t JOIN onboarding_step_versions v ON v.id = t.step_version_id
                                JOIN onboarding_steps s ON s.id = v.step_id WHERE t.user_id=%s ORDER BY s.position""", user["id"])
    return {"application": {**app, "messages": await thread(conn, app["id"])}, "fields": await get_fields(conn, only_active=False), "accepted_terms": accepted}


@router.get("/export", summary="Download ALL company data (documents + conversations, questions, feedback, reports) as a ZIP")
async def export_all(ctx=Depends(CA, scope="function")):
    user, conn = ctx
    cid = user["company_id"]
    docs = await q(conn, "SELECT filename, storage_path FROM documents WHERE company_id=%s ORDER BY created_at", cid)
    convs = await an.conversation_export_rows(conn, cid)
    questions = await an.questions_report(conn, cid, 100000)
    feedback = await an.feedback_list(conn, cid, 100000, 0)
    reports = await an.reports_list(conn, cid, None, 100000, 0)
    tmp = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for i, d in enumerate(docs, 1):
            path = Path(d["storage_path"])
            if path.exists():
                z.write(path, f"documents/{i:03d}_{re.sub(r'[^A-Za-z0-9._-]', '_', d['filename'])}")
        def put(name, rows, cols=None):
            cols = cols or (list(rows[0].keys()) if rows else ["(empty)"])
            z.writestr(name, an.to_csv(rows, cols))
        put("conversations.csv", convs, an.EXPORT_COLUMNS)
        put("questions.csv", questions, ["question", "times_asked", "found_info", "not_found", "information_present", "last_asked"])
        put("feedback.csv", feedback, ["created_at", "employee", "evaluation_question", "rating", "bool_value", "question", "answer"])
        put("reports.csv", reports, ["created_at", "employee", "type", "comments", "status"])
        z.writestr("README.txt", "Export of your company's data from the Company RAG platform.\n"
                                  "documents/ = the original files you uploaded. The CSV files contain questions, answers, feedback and reported cases.\n"
                                  "Keep this file safe: ending the service permanently deletes the data on the platform.\n")
    tmp.seek(0)
    await audit(conn, user["id"], "data.export", company_id=cid, details={"documents": len(docs)})
    return StreamingResponse(iter(lambda: tmp.read(1 << 20), b""), media_type="application/zip",
                             headers={"Content-Disposition": 'attachment; filename="company-data-export.zip"'})
