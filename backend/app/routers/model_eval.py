"""SuperAdmin model-evaluation lab: benchmark datasets (documents + questions with ground truth),
evaluation runs (embedding/retrieval or LLM) and their per-case results."""
import json
import re
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from psycopg.types.json import Jsonb

from ..db import ex, q, q1
from ..deps import SA
from ..errors import err
from ..schemas import EvalCaseIn, EvalDatasetIn, EvalRunIn
from ..services import analytics as an
from ..services.common import audit
from ..settings import settings

router = APIRouter(prefix="/superadmin/model-eval", tags=["SuperAdmin - Model Evaluation"])
ALLOWED = {"pdf", "docx", "txt", "md"}
MAX_MB = 10


def _folder(dataset_id) -> Path:
    return Path(settings.storage_dir) / "_eval" / str(dataset_id)


async def _dataset(conn, dataset_id):
    ds = await q1(conn, "SELECT * FROM eval_datasets WHERE id=%s", dataset_id)
    if not ds:
        raise err(404, "dataset_not_found", "Dataset not found.")
    return ds


# ------------------------------ datasets ------------------------------
@router.get("/datasets", summary="Benchmark datasets")
async def list_datasets(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, """SELECT d.id, d.name, d.description, d.is_starter, d.created_at,
        (SELECT count(*) FROM eval_documents WHERE dataset_id = d.id) AS documents,
        (SELECT count(*) FROM eval_cases WHERE dataset_id = d.id) AS cases,
        (SELECT count(*) FROM eval_cases WHERE dataset_id = d.id AND answerable) AS answerable_cases
        FROM eval_datasets d ORDER BY d.is_starter DESC, d.created_at""")


@router.post("/datasets", status_code=201, summary="Create an empty dataset")
async def create_dataset(body: EvalDatasetIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    ds = await q1(conn, "INSERT INTO eval_datasets (name, description, created_by) VALUES (%s,%s,%s) RETURNING id, name, description", body.name, body.description, user["id"])
    company = await q1(conn, "INSERT INTO companies (name, is_system, access_status) VALUES (%s, TRUE, 'inactive') RETURNING id", f"[System] Evaluation workspace {ds['id']}")
    await ex(conn, "UPDATE eval_datasets SET company_id=%s WHERE id=%s", company["id"], ds["id"])
    await audit(conn, user["id"], "model_eval.dataset.create", target_type="eval_dataset", target_id=ds["id"])
    return ds


@router.get("/datasets/{dataset_id}", summary="Dataset with its documents and questions")
async def get_dataset(dataset_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    ds = await _dataset(conn, dataset_id)
    docs = await q(conn, "SELECT id, filename, file_type, language, size_bytes, (document_id IS NOT NULL AND ingest_fingerprint IS NOT NULL) AS processed FROM eval_documents WHERE dataset_id=%s ORDER BY filename", dataset_id)
    cases = await q(conn, "SELECT * FROM eval_cases WHERE dataset_id=%s ORDER BY position, created_at", dataset_id)
    return {**{k: ds[k] for k in ("id", "name", "description", "is_starter", "created_at")}, "documents": docs, "cases": cases}


@router.put("/datasets/{dataset_id}")
async def update_dataset(dataset_id: UUID, body: EvalDatasetIn, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    row = await q1(conn, "UPDATE eval_datasets SET name=%s, description=%s WHERE id=%s RETURNING id, name, description", body.name, body.description, dataset_id)
    if not row:
        raise err(404, "dataset_not_found", "Dataset not found.")
    return row


@router.delete("/datasets/{dataset_id}", summary="Delete a dataset, its runs and its hidden workspace")
async def delete_dataset(dataset_id: UUID, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    ds = await _dataset(conn, dataset_id)
    if await q1(conn, "SELECT 1 FROM eval_runs WHERE dataset_id=%s AND status IN ('queued','running')", dataset_id):
        raise err(409, "run_in_progress", "A run is in progress for this dataset. Wait for it to finish.")
    await ex(conn, "DELETE FROM eval_datasets WHERE id=%s", dataset_id)
    if ds["company_id"]:
        await ex(conn, "DELETE FROM companies WHERE id=%s AND is_system", ds["company_id"])
    shutil.rmtree(_folder(dataset_id), ignore_errors=True)
    await audit(conn, user["id"], "model_eval.dataset.delete", target_type="eval_dataset", target_id=dataset_id)
    return {"ok": True}


# ------------------------------ documents ------------------------------
@router.post("/datasets/{dataset_id}/documents", status_code=202, summary="Upload benchmark documents (PDF, DOCX, TXT, MD)")
async def upload_documents(dataset_id: UUID, files: list[UploadFile] = File(...), language: Optional[str] = Form(None), ctx=Depends(SA, scope="function")):
    user, conn = ctx
    await _dataset(conn, dataset_id)
    if language and not re.fullmatch(r"[a-z]{2,3}", language):
        raise err(422, "invalid_language", "Language must be a 2-3 letter code such as en or rw.")
    folder = _folder(dataset_id)
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for f in files:
        name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(f.filename or "file").name)
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ALLOWED:
            results.append({"filename": name, "status": "rejected", "reason": f"Type .{ext} is not allowed ({', '.join(sorted(ALLOWED))})."})
            continue
        data = await f.read(MAX_MB * 1024 * 1024 + 1)
        if not data or len(data) > MAX_MB * 1024 * 1024:
            results.append({"filename": name, "status": "rejected", "reason": f"File is empty or larger than {MAX_MB} MB."})
            continue
        if await q1(conn, "SELECT 1 FROM eval_documents WHERE dataset_id=%s AND filename=%s", dataset_id, name):
            results.append({"filename": name, "status": "rejected", "reason": "A document with this name already exists in the dataset."})
            continue
        path = folder / name
        path.write_bytes(data)
        await ex(conn, "INSERT INTO eval_documents (dataset_id, filename, file_type, language, storage_path, size_bytes) VALUES (%s,%s,%s,%s,%s,%s)", dataset_id, name, ext, language, str(path), len(data))
        results.append({"filename": name, "status": "added"})
    return {"results": results}


@router.delete("/datasets/{dataset_id}/documents/{doc_id}")
async def delete_document(dataset_id: UUID, doc_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    ed = await q1(conn, "SELECT * FROM eval_documents WHERE id=%s AND dataset_id=%s", doc_id, dataset_id)
    if not ed:
        raise err(404, "document_not_found", "Document not found.")
    if ed["document_id"]:
        await ex(conn, "DELETE FROM documents WHERE id=%s", ed["document_id"])        # cascades its chunks
    await ex(conn, "DELETE FROM eval_documents WHERE id=%s", doc_id)
    Path(ed["storage_path"]).unlink(missing_ok=True)
    return {"ok": True}


# ------------------------------ questions (cases) ------------------------------
async def _next_position(conn, dataset_id):
    return (await q1(conn, "SELECT coalesce(max(position), 0) + 1 AS n FROM eval_cases WHERE dataset_id=%s", dataset_id))["n"]


def _case_values(b: EvalCaseIn):
    return (b.question, b.question_language, b.document_language if b.answerable else None, b.answerable, b.expected_answer, Jsonb(b.evidence if b.answerable else []), Jsonb(b.key_facts))


@router.post("/datasets/{dataset_id}/cases", status_code=201, summary="Add a question with its ground truth")
async def add_case(dataset_id: UUID, body: EvalCaseIn, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    await _dataset(conn, dataset_id)
    return await q1(conn, """INSERT INTO eval_cases (dataset_id, position, question, question_language, document_language, answerable, expected_answer, evidence, key_facts)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""", dataset_id, await _next_position(conn, dataset_id), *_case_values(body))


@router.put("/cases/{case_id}")
async def update_case(case_id: UUID, body: EvalCaseIn, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    row = await q1(conn, """UPDATE eval_cases SET question=%s, question_language=%s, document_language=%s, answerable=%s, expected_answer=%s, evidence=%s, key_facts=%s
                            WHERE id=%s RETURNING *""", *_case_values(body), case_id)
    if not row:
        raise err(404, "case_not_found", "Question not found.")
    return row


@router.delete("/cases/{case_id}")
async def delete_case(case_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    await ex(conn, "DELETE FROM eval_cases WHERE id=%s", case_id)
    return {"ok": True}


@router.post("/datasets/{dataset_id}/cases/import", summary="Import many questions at once (JSON list)")
async def import_cases(dataset_id: UUID, cases: list[EvalCaseIn], replace: bool = False, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    await _dataset(conn, dataset_id)
    if replace:
        await ex(conn, "DELETE FROM eval_cases WHERE dataset_id=%s", dataset_id)
    pos = await _next_position(conn, dataset_id)
    for i, c in enumerate(cases):
        await ex(conn, """INSERT INTO eval_cases (dataset_id, position, question, question_language, document_language, answerable, expected_answer, evidence, key_facts)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", dataset_id, pos + i, *_case_values(c))
    return {"imported": len(cases)}


@router.get("/datasets/{dataset_id}/cases/export", summary="Export the questions as JSON (re-importable)")
async def export_cases(dataset_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    rows = await q(conn, "SELECT question, question_language, document_language, answerable, expected_answer, evidence, key_facts FROM eval_cases WHERE dataset_id=%s ORDER BY position", dataset_id)
    return Response(json.dumps(rows, indent=2, ensure_ascii=False), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="eval_cases.json"'})


# ------------------------------ runs ------------------------------
@router.post("/runs", status_code=202, summary="Start an evaluation run (executed by the background worker)")
async def start_run(body: EvalRunIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    await _dataset(conn, body.dataset_id)
    n_docs = (await q1(conn, "SELECT count(*) AS n FROM eval_documents WHERE dataset_id=%s", body.dataset_id))["n"]
    n_cases = (await q1(conn, "SELECT count(*) AS n FROM eval_cases WHERE dataset_id=%s", body.dataset_id))["n"]
    if not n_docs or not n_cases:
        raise err(409, "dataset_incomplete", "Add at least one document and one question to the dataset first.")
    if await q1(conn, "SELECT 1 FROM eval_runs WHERE status IN ('queued','running') AND dataset_id=%s", body.dataset_id):
        raise err(409, "run_in_progress", "A run is already in progress for this dataset.")
    run = await q1(conn, "INSERT INTO eval_runs (dataset_id, kind, params, created_by) VALUES (%s,%s,%s,%s) RETURNING id, kind, status",
                   body.dataset_id, body.kind, Jsonb(body.params.model_dump()), user["id"])
    await audit(conn, user["id"], "model_eval.run.start", target_type="eval_run", target_id=run["id"], details={"kind": body.kind})
    return run


@router.get("/runs", summary="Evaluation runs with headline numbers")
async def list_runs(dataset_id: Optional[UUID] = None, kind: Optional[str] = None, limit: int = Query(50, le=200), ctx=Depends(SA, scope="function")):
    _, conn = ctx
    where, args = ["true"], []
    if dataset_id:
        where.append("r.dataset_id = %s"); args.append(dataset_id)
    if kind:
        where.append("r.kind = %s"); args.append(kind)
    return await q(conn, f"""SELECT r.id, r.dataset_id, d.name AS dataset, r.kind, r.status, r.progress_pct, r.message, r.params, r.error, r.created_at, r.finished_at,
        r.config_snapshot #>> '{{embedding,model}}' AS embedding_model, r.config_snapshot #>> '{{llm,model}}' AS llm_model,
        r.summary #>> '{{modes,hybrid,hit@5}}' AS hybrid_hit5, r.summary #>> '{{modes,hybrid,mrr}}' AS hybrid_mrr,
        r.summary #>> '{{key_fact_recall}}' AS key_fact_recall, r.summary #>> '{{faithfulness}}' AS faithfulness
        FROM eval_runs r JOIN eval_datasets d ON d.id = r.dataset_id WHERE {' AND '.join(where)} ORDER BY r.created_at DESC LIMIT %s""", *args, limit)


@router.get("/runs/{run_id}", summary="One run: settings evaluated, progress and aggregated metrics")
async def get_run(run_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    row = await q1(conn, "SELECT r.*, d.name AS dataset FROM eval_runs r JOIN eval_datasets d ON d.id = r.dataset_id WHERE r.id=%s", run_id)
    if not row:
        raise err(404, "run_not_found", "Run not found.")
    return row


@router.get("/runs/{run_id}/cases", summary="Per-question results")
async def run_cases(run_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, """SELECT r.id, r.case_id, r.question, r.metrics, r.details, c.position FROM eval_case_results r
                            LEFT JOIN eval_cases c ON c.id = r.case_id WHERE r.run_id=%s ORDER BY c.position NULLS LAST, r.created_at""", run_id)


@router.delete("/runs/{run_id}")
async def delete_run(run_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    if await q1(conn, "SELECT 1 FROM eval_runs WHERE id=%s AND status IN ('queued','running')", run_id):
        raise err(409, "run_in_progress", "This run is still in progress.")
    await ex(conn, "DELETE FROM eval_runs WHERE id=%s", run_id)
    return {"ok": True}


def _flat(prefix, d, out):
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            _flat(f"{prefix}{k}.", v, out)
        elif not isinstance(v, (list,)):
            out[f"{prefix}{k}"] = v


@router.get("/runs/{run_id}/export", summary="Per-question metrics as CSV")
async def export_run(run_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    rows = await run_cases(run_id, ctx)
    flat = []
    for r in rows:
        f = {"question": r["question"]}
        _flat("", r["metrics"], f)
        flat.append(f)
    cols = ["question"] + sorted({k for f in flat for k in f} - {"question"})
    return Response(an.to_csv(flat, cols), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="evaluation_{run_id}.csv"'})
