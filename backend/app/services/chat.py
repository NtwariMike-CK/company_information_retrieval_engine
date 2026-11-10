"""Employee question -> grounded answer. Implements the workflow in the project spec (section 5)."""
import re, time

from ..db import ex, q, q1, tx
from ..errors import err
from ..rag.ai import AIError, RateLimitError, get_embedder, get_llm
from ..rag.lang import load_detector
from ..rag.retrieval import QUERY_TRANSFORM_FUNCS, load_context, retrieve
from .common import log_error
from .config_service import get_active, resolve_key


def normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def language_directive(lang: str | None, names: dict) -> str:
    """Explicit instruction so the answer language never depends on the configured prompt alone."""
    if lang and lang in names:
        return f"Respond in {names[lang]}."
    return "Respond in the same language as the employee's question."


def build_user_prompt(question: str, contexts: list[dict], directive: str = "") -> str:
    tail = f"\n\n{directive}" if directive else ""
    if not contexts:
        return f"<context>No relevant context was found in the company knowledge base.</context>\n\nEmployee question: {question}{tail}"
    blocks = []
    for i, c in enumerate(contexts, 1):
        src = c["filename"] + (f", page {c['page']}" if c["page"] else "")
        blocks.append(f"[{i}] Source: {src}\n{c['text']}")
    return "<context>\n" + "\n\n".join(blocks) + f"\n</context>\n\nEmployee question: {question}{tail}"


async def ask(user: dict, conversation_id, question: str) -> dict:
    cid, uid = user["company_id"], user["id"]

    # 1) Authenticate (done by dependency) + Validate: service active, chat limit
    async with tx(company_id=cid) as conn:
        company = await q1(conn, "SELECT chatbot_state FROM companies WHERE id=%s", cid)
        if company["chatbot_state"] != "started":
            msg = {"paused": "The assistant is currently paused by your company administrator.",
                   "ended": "This company's service has ended."}.get(company["chatbot_state"], "The assistant has not been started yet.")
            raise err(403, "service_unavailable", msg)
        cfg = await get_active(conn)
        conv = await q1(conn, "SELECT * FROM conversations WHERE id=%s AND user_id=%s AND company_id=%s", conversation_id, uid, cid)
        if not conv:
            raise err(404, "conversation_not_found", "Conversation not found.")
        if conv["exchange_count"] >= cfg.chat_cfg.max_exchanges:
            raise err(409, "chat_limit_reached", f"This chat has reached its limit of {cfg.chat_cfg.max_exchanges} questions. Please start a new chat.")
        history = await q(conn, "SELECT role, content FROM messages WHERE conversation_id=%s ORDER BY exchange_no, role", conversation_id)

    detector = await load_detector()
    qlang = detector.detect(question)
    if qlang is None:      # very short follow-ups ("na none?"): keep the language of the previous question
        for m in reversed(history):
            if m["role"] == "user" and detector.detect(m["content"]):
                qlang = detector.detect(m["content"])
                break
    t0 = time.perf_counter()
    try:
        # 2) Embed  3) Retrieve  4) Rank
        qtext = question
        if cfg.retrieval_cfg.query_transform:
            qtext = QUERY_TRANSFORM_FUNCS[cfg.retrieval_cfg.query_transform](question, history)
        vec = None
        async with tx(company_id=cid) as conn:
            ekey = await resolve_key(conn, cfg.embedding_cfg.credential_id) if cfg.embedding_cfg.provider == "google" else ""
            lkey = await resolve_key(conn, cfg.llm_cfg.credential_id) if cfg.llm_cfg.provider == "google" else ""
        if cfg.retrieval_cfg.dense.enabled:
            vec = (await get_embedder(cfg.embedding_cfg, ekey).embed([qtext], "RETRIEVAL_QUERY"))[0]
        async with tx(company_id=cid) as conn:
            fused, has_evidence = await retrieve(conn, cid, qtext, vec, cfg.retrieval_cfg, cfg.embedding_cfg.model, detector.stopwords)
            contexts = await load_context(conn, [c["id"] for c in fused]) if has_evidence else []
        # 6) Generate (no-evidence path uses the configured no-evidence prompt)
        t_ret = time.perf_counter()
        system = cfg.prompt_cfg.system_prompt if has_evidence else cfg.prompt_cfg.no_evidence_prompt
        result = await get_llm(cfg.llm_cfg, lkey).generate(system, history[-16:], build_user_prompt(question, contexts, language_directive(qlang, detector.names)))
    except RateLimitError as e:
        await log_error("llm", "rate_limit", "provider rate limit", repr(e), cid)
        raise err(429, "rate_limit", cfg.messages_cfg.for_lang("rate_limit", qlang))
    except AIError as e:
        await log_error("llm", "ai_failure", "AI service failure", repr(e), cid)
        raise err(502, "ai_failure", cfg.messages_cfg.for_lang("ai_failure", qlang))
    t_end = time.perf_counter()
    latency = int((t_end - t0) * 1000)
    timing = {"retrieval_s": round(t_ret - t0, 3), "generation_s": round(t_end - t_ret, 3), "total_s": round(t_end - t0, 3)}

    # 8) Record: question, answer, retrieval evidence, usage
    async with tx(company_id=cid) as conn:
        conv = await q1(conn, "SELECT * FROM conversations WHERE id=%s FOR UPDATE", conversation_id)
        if conv["exchange_count"] >= cfg.chat_cfg.max_exchanges:      # re-check after the slow AI call (race safe)
            raise err(409, "chat_limit_reached", "This chat has reached its question limit. Please start a new chat.")
        n = conv["exchange_count"] + 1
        await ex(conn, """INSERT INTO messages (conversation_id, company_id, user_id, role, exchange_no, content, normalized_question, language)
                          VALUES (%s,%s,%s,'user',%s,%s,%s,%s)""", conversation_id, cid, uid, n, question, normalize_question(question), qlang)
        a = await q1(conn, """INSERT INTO messages (conversation_id, company_id, user_id, role, exchange_no, content, has_evidence,
                              config_version_id, model_name, prompt_tokens, completion_tokens, latency_ms)
                              VALUES (%s,%s,%s,'assistant',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, created_at""",
                     conversation_id, cid, uid, n, result.text, has_evidence, cfg.id, cfg.llm_cfg.model,
                     result.prompt_tokens, result.completion_tokens, latency)
        used = {c["chunk_id"] for c in contexts}
        for rank, c in enumerate(fused, 1):
            await ex(conn, """INSERT INTO retrieval_logs (message_id, company_id, chunk_id, parent_id, rank, dense_score, sparse_score, fused_score, used_in_prompt)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", a["id"], cid, c["id"], c["parent_id"], rank,
                     c["dense_score"], c["sparse_score"], c["fused_score"], c["id"] in used)
        title = conv["title"] or question[:80]
        await ex(conn, "UPDATE conversations SET exchange_count=%s, title=%s, updated_at=now() WHERE id=%s", n, title, conversation_id)
        es = await q1(conn, "SELECT every_n_answers, enabled FROM evaluation_settings WHERE id=1")
        requested = bool(es["enabled"]) and n % es["every_n_answers"] == 0
        eval_questions = await q(conn, "SELECT id, text, type FROM evaluation_questions WHERE is_active ORDER BY position, created_at") if requested else []

    return {"message_id": a["id"], "exchange_no": n, "answer": result.text, "has_evidence": has_evidence,
            "remaining_exchanges": cfg.chat_cfg.max_exchanges - n, "language": qlang, "timing": timing,
            "sources": [{"filename": c["filename"], "page": c["page"]} for c in contexts],
            "evaluation": {"requested": requested and bool(eval_questions), "questions": eval_questions}}
