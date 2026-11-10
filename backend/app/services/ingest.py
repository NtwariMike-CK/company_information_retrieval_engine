"""Document ingestion: extract -> clean (+EDA) -> chunk -> embed -> index. Runs inside the worker."""
import asyncio, uuid

from psycopg.types.json import Jsonb

from ..db import ex, q1, tx
from ..rag.ai import get_embedder
from ..rag.chunking import chunk_pages
from ..rag.clean import clean_pages
from ..rag.extract import ExtractionError, extract_pages
from ..rag.lang import load_detector
from ..rag.retrieval import vec_literal
from ..schemas import MessagesCfg
from ..settings import settings
from .common import log_error, recompute_kb_status
from .config_service import get_active, resolve_key


def batched(items: list, size: int):
    """Split a list into consecutive batches of at most `size` items (used for embedding calls)."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


async def _progress(job_id, stage, pct, eda=None):
    async with tx(bypass=True) as conn:
        if eda is not None:
            await ex(conn, "UPDATE processing_jobs SET stage=%s, progress_pct=%s, eda_stats=%s WHERE id=%s",
                     stage, pct, Jsonb(eda), job_id)
        else:
            await ex(conn, "UPDATE processing_jobs SET stage=%s, progress_pct=%s WHERE id=%s", stage, pct, job_id)


async def process_job(job: dict):
    job_id, doc_id, cid = job["id"], job["document_id"], job["company_id"]
    safe_msg = MessagesCfg().processing_failure
    try:
        async with tx(bypass=True) as conn:
            doc = await q1(conn, "SELECT * FROM documents WHERE id=%s", doc_id)
            if not doc:
                return
            cfg = await get_active(conn)
            safe_msg = cfg.messages_cfg.processing_failure
            key = await resolve_key(conn, cfg.embedding_cfg.credential_id) if cfg.embedding_cfg.provider == "google" else ""
            await ex(conn, "UPDATE documents SET status='processing', error_message=NULL, config_version_id=%s WHERE id=%s",
                     cfg.id, doc_id)

        detector = await load_detector()
        await _progress(job_id, "extract", 5)
        pages = await asyncio.to_thread(extract_pages, doc["storage_path"], doc["file_type"])
        await _progress(job_id, "clean", 20)
        pages, eda = await asyncio.to_thread(clean_pages, pages, cfg.cleaning_cfg, doc["file_type"], detector)
        if not any(t.strip() for _, t in pages):
            raise ExtractionError("document is empty after cleaning")
        await _progress(job_id, "chunk", 30, eda)
        parents, children = await asyncio.to_thread(chunk_pages, pages, cfg.chunking_cfg, detector)
        if not children:
            raise ExtractionError("no chunks produced")
        eda.update({"parent_chunks": len(parents), "chunks": len(children), "chunking": cfg.chunking_cfg.strategy})
        await _progress(job_id, "embed", 40, eda)

        embedder, bs, vectors = get_embedder(cfg.embedding_cfg, key), cfg.embedding_cfg.batch_size, []
        for i in range(0, len(children), bs):
            vectors += await embedder.embed([c["content"] for c in children[i:i + bs]], "RETRIEVAL_DOCUMENT")
            await _progress(job_id, "embed", 40 + int(50 * min(i + bs, len(children)) / len(children)))
            if settings.embed_pause_seconds and i + bs < len(children):
                await asyncio.sleep(settings.embed_pause_seconds)   # stay under provider rate limits

        await _progress(job_id, "index", 92)
        pid = [uuid.uuid4() for _ in parents]
        async with tx(bypass=True) as conn:
            await ex(conn, "DELETE FROM chunks WHERE document_id=%s", doc_id)          # idempotent retries
            await ex(conn, "DELETE FROM parent_chunks WHERE document_id=%s", doc_id)
            async with conn.cursor() as cur:
                if parents:
                    await cur.executemany(
                        "INSERT INTO parent_chunks (id, company_id, document_id, chunk_index, content, page_number, token_count) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        [(pid[p["index"]], cid, doc_id, p["index"], p["content"], p["page"], len(p["content"]) // 4) for p in parents])
                await cur.executemany(
                    "INSERT INTO chunks (company_id, document_id, parent_id, chunk_index, content, token_count, metadata, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                    [(cid, doc_id, pid[c["parent_index"]] if c["parent_index"] is not None else None, c["index"], c["content"],
                      len(c["content"]) // 4, Jsonb({"page": c["page"], "lang": c.get("lang")}), vec_literal(v)) for c, v in zip(children, vectors)])
            await ex(conn, "UPDATE documents SET status='ready', embedding_model=%s WHERE id=%s", cfg.embedding_cfg.model, doc_id)
            await ex(conn, "UPDATE processing_jobs SET stage='done', status='succeeded', progress_pct=100, finished_at=now() WHERE id=%s", job_id)
            await recompute_kb_status(conn, cid)
    except Exception as e:
        await log_error("ingestion", type(e).__name__, f"job {job_id} failed", repr(e), cid)
        async with tx(bypass=True) as conn:
            await ex(conn, "UPDATE documents SET status='failed', error_message=%s WHERE id=%s", safe_msg, doc_id)
            await ex(conn, "UPDATE processing_jobs SET status='failed', error_message=%s, error_detail=%s, finished_at=now() WHERE id=%s",
                     safe_msg, repr(e)[:2000], job_id)
            await recompute_kb_status(conn, cid)
