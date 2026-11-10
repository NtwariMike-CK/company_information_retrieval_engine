"""Hybrid retrieval: dense (pgvector cosine) + sparse (Postgres full-text) fused with RRF.
Every query is explicitly scoped by company_id (RLS is a second layer)."""
import re

from ..db import q

STOP = set("a an the is are was were be been to of in on for and or what how do does did can could i my we our you "
           "your with at by from as it its this that these those about which who whom when where why will would "
           "should shall me us them they he she there here if then than so not no".split())


def or_query(text: str, extra_stopwords=None) -> str:
    """OR-query over letter/digit tokens (unicode-safe). Stopwords of every enabled language are removed."""
    stop = STOP | set(extra_stopwords or ())
    words, seen = [], set()
    for w in re.findall(r"[^\W_]+", text.lower()):
        if w not in stop and len(w) > 1 and w not in seen:
            seen.add(w)
            words.append(w)
    return " | ".join(words[:30])


def vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


async def dense_search(conn, company_id, vec, k, embedding_model):
    lit = vec_literal(vec)
    try:
        async with conn.transaction():   # savepoint: iterative scan needs pgvector >= 0.8
            await conn.execute("SELECT set_config('hnsw.iterative_scan','relaxed_order',true)")
    except Exception:
        pass
    # only compare against vectors made by the SAME embedding model (different models are not comparable)
    rows = await q(conn, """SELECT c.id, c.parent_id, 1 - (c.embedding <=> %s::vector) AS score
                            FROM chunks c JOIN documents d ON d.id = c.document_id
                            WHERE c.company_id = %s AND c.embedding IS NOT NULL AND d.embedding_model = %s
                            ORDER BY c.embedding <=> %s::vector LIMIT %s""", lit, company_id, embedding_model, lit, k)
    return sorted(rows, key=lambda r: -r["score"])


async def sparse_search(conn, company_id, text, k, stopwords=None):
    tsq = or_query(text, stopwords)
    if not tsq:
        return []
    # 'simple' matches raw tokens in any language (Kinyarwanda, English); 'english' adds stemming for English
    return await q(conn, """SELECT id, parent_id, ts_rank_cd(tsv, (to_tsquery('simple', %s) || to_tsquery('english', %s))) AS score
                            FROM chunks
                            WHERE company_id = %s AND tsv @@ (to_tsquery('simple', %s) || to_tsquery('english', %s))
                            ORDER BY score DESC LIMIT %s""", tsq, tsq, company_id, tsq, tsq, k)


def rrf_fuse(dense, sparse, k=60):
    cands = {}
    for rows, key in ((dense, "dense_score"), (sparse, "sparse_score")):
        for rank, r in enumerate(rows, 1):
            c = cands.setdefault(r["id"], {"id": r["id"], "parent_id": r["parent_id"], "dense_score": None,
                                            "sparse_score": None, "fused_score": 0.0})
            c[key] = float(r["score"])
            c["fused_score"] += 1.0 / (k + rank)
    return sorted(cands.values(), key=lambda c: -c["fused_score"])


# ---- pluggable query transformation (slot for LLM-based rewriting later) ----
def followup_concat(question: str, history: list[dict]) -> str:
    """Short follow-ups ('and for contractors?') lack context: prepend the previous user question."""
    prev = [m["content"] for m in history if m["role"] == "user"]
    if prev and len(question.split()) < 8:
        return f"{prev[-1]} {question}"
    return question


QUERY_TRANSFORM_FUNCS = {"followup_concat": followup_concat}


async def retrieve(conn, company_id, question_text, vec, cfg, embedding_model, stopwords=None):
    dense = await dense_search(conn, company_id, vec, cfg.dense.top_k, embedding_model) if cfg.dense.enabled and vec else []
    sparse = await sparse_search(conn, company_id, question_text, cfg.sparse.top_k, stopwords) if cfg.sparse.enabled else []
    fused = rrf_fuse(dense, sparse, cfg.rrf_k)[: cfg.final_k]
    if cfg.dense.enabled:
        has_evidence = any(c["dense_score"] is not None and c["dense_score"] >= cfg.min_score for c in fused)
    else:
        has_evidence = bool(fused)
    return fused, has_evidence


async def load_context(conn, chunk_ids, max_chars=12000):
    rows = await q(conn, """SELECT c.id, c.content AS child, pc.id AS parent_id, pc.content AS parent,
                                   COALESCE(pc.page_number, (c.metadata->>'page')::int) AS page, d.filename
                            FROM chunks c JOIN documents d ON d.id = c.document_id
                            LEFT JOIN parent_chunks pc ON pc.id = c.parent_id
                            WHERE c.id = ANY(%s::uuid[])""", chunk_ids)
    by_id = {r["id"]: r for r in rows}
    out, seen_parents, total = [], set(), 0
    for cid in chunk_ids:                      # keep ranking order
        r = by_id.get(cid)
        if not r:
            continue
        if r["parent_id"]:
            if r["parent_id"] in seen_parents:
                continue
            seen_parents.add(r["parent_id"])
        text = r["parent"] or r["child"]       # parent-child: search small, answer with big
        if total + len(text) > max_chars:
            break
        total += len(text)
        out.append({"chunk_id": cid, "text": text, "filename": r["filename"], "page": r["page"]})
    return out
