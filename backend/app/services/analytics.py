import csv, io

from ..db import q, q1


def _w(alias: str, cid, extra_args=()):
    return (f"AND {alias}.company_id = %s", (cid, *extra_args)) if cid else ("", tuple(extra_args))


def csv_safe(v):
    """Neutralise spreadsheet formula injection in exported cells."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def to_csv(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow([csv_safe(r.get(c)) for c in columns])
    return buf.getvalue()


async def overview(conn, cid=None):
    wc, p = _w("m", cid)
    msgs = await q1(conn, f"""SELECT count(*) FILTER (WHERE role='user') AS questions,
        count(*) FILTER (WHERE role='assistant' AND has_evidence) AS answered_with_evidence,
        count(*) FILTER (WHERE role='assistant' AND NOT has_evidence) AS no_evidence,
        coalesce(sum(prompt_tokens),0) AS prompt_tokens, coalesce(sum(completion_tokens),0) AS completion_tokens,
        round(avg(latency_ms) FILTER (WHERE role='assistant')) AS avg_latency_ms FROM messages m WHERE true {wc}""", *p)
    wc, p = _w("c", cid)
    convs = await q1(conn, f"SELECT count(*) AS conversations FROM conversations c WHERE true {wc}", *p)
    wc, p = _w("f", cid)
    fb = await q1(conn, f"""SELECT round(avg(rating)::numeric,2) AS avg_rating, count(rating) AS rating_count,
        count(*) FILTER (WHERE bool_value) AS true_count, count(*) FILTER (WHERE bool_value IS NOT NULL AND NOT bool_value) AS false_count
        FROM feedback f WHERE true {wc}""", *p)
    dist = await q(conn, f"SELECT rating, count(*) AS n FROM feedback f WHERE rating IS NOT NULL {wc} GROUP BY rating ORDER BY rating", *p)
    wc, p = _w("r", cid)
    reports = await q(conn, f"SELECT status, count(*) AS n FROM reports r WHERE true {wc} GROUP BY status", *p)
    wc, p = _w("d", cid)
    docs = await q(conn, f"SELECT d.status, count(*) AS n FROM documents d JOIN companies co ON co.id = d.company_id WHERE NOT co.is_system {wc} GROUP BY d.status", *p)
    wc, p = _w("e", cid)
    errors = await q(conn, f"""SELECT source, error_code, count(*) AS n FROM error_logs e
                               WHERE created_at > now() - interval '30 days' {wc} GROUP BY 1,2 ORDER BY n DESC""", *p)
    return {**msgs, **convs, **fb, "rating_distribution": dist, "reports_by_status": reports,
            "documents_by_status": docs, "errors_last_30_days": errors}


async def per_company(conn):
    return await q(conn, """SELECT c.id, c.name, c.access_status, c.chatbot_state, c.kb_status,
        (SELECT count(*) FROM messages m WHERE m.company_id=c.id AND m.role='user') AS questions,
        (SELECT count(*) FROM messages m WHERE m.company_id=c.id AND m.role='assistant' AND NOT m.has_evidence) AS no_evidence,
        (SELECT round(avg(rating)::numeric,2) FROM feedback f WHERE f.company_id=c.id) AS avg_rating,
        (SELECT count(*) FROM reports r WHERE r.company_id=c.id AND r.status='open') AS open_reports,
        (SELECT count(*) FROM documents d WHERE d.company_id=c.id AND d.status='failed') AS failed_documents
        FROM companies c WHERE NOT c.is_system ORDER BY c.name""")


async def questions_report(conn, cid=None, limit=500):
    wc, p = _w("u", cid)
    return await q(conn, f"""SELECT min(u.content) AS question, count(*) AS times_asked,
        count(*) FILTER (WHERE a.has_evidence) AS found_info, count(*) FILTER (WHERE NOT a.has_evidence) AS not_found,
        bool_or(a.has_evidence) AS information_present, max(u.created_at) AS last_asked
        FROM messages u JOIN messages a ON a.conversation_id=u.conversation_id AND a.exchange_no=u.exchange_no AND a.role='assistant'
        WHERE u.role='user' {wc} GROUP BY u.normalized_question ORDER BY times_asked DESC, last_asked DESC LIMIT %s""", *p, limit)


async def feedback_list(conn, cid=None, limit=50, offset=0):
    wc, p = _w("f", cid)
    return await q(conn, f"""SELECT f.id, f.created_at, co.name AS company, u.full_name AS employee, u.email,
        eq.text AS evaluation_question, eq.type AS evaluation_type, f.rating, f.bool_value,
        qm.content AS question, am.content AS answer, am.id AS message_id, am.conversation_id
        FROM feedback f JOIN users u ON u.id=f.user_id JOIN companies co ON co.id=f.company_id
        JOIN evaluation_questions eq ON eq.id=f.question_id JOIN messages am ON am.id=f.message_id
        JOIN messages qm ON qm.conversation_id=am.conversation_id AND qm.exchange_no=am.exchange_no AND qm.role='user'
        WHERE true {wc} ORDER BY f.created_at DESC LIMIT %s OFFSET %s""", *p, limit, offset)


async def reports_list(conn, cid=None, status=None, limit=50, offset=0):
    wc, p = _w("r", cid)
    if status:
        wc += " AND r.status = %s"
        p += (status,)
    return await q(conn, f"""SELECT r.id, r.created_at, r.type, r.comments, r.status, r.conversation_id, r.message_id,
        co.name AS company, u.full_name AS employee, u.email,
        qm.content AS question, am.content AS answer
        FROM reports r JOIN users u ON u.id=r.user_id JOIN companies co ON co.id=r.company_id
        LEFT JOIN messages am ON am.id=r.message_id
        LEFT JOIN messages qm ON qm.conversation_id=am.conversation_id AND qm.exchange_no=am.exchange_no AND qm.role='user'
        WHERE true {wc} ORDER BY r.created_at DESC LIMIT %s OFFSET %s""", *p, limit, offset)


async def conversations_list(conn, cid=None, limit=50, offset=0):
    wc, p = _w("c", cid)
    return await q(conn, f"""SELECT c.id, c.title, c.exchange_count, c.created_at, c.updated_at, co.name AS company,
        u.full_name AS employee, u.email,
        (SELECT round(avg(f.rating)::numeric,2) FROM feedback f JOIN messages m ON m.id=f.message_id WHERE m.conversation_id=c.id) AS avg_score
        FROM conversations c JOIN users u ON u.id=c.user_id JOIN companies co ON co.id=c.company_id
        WHERE true {wc} ORDER BY c.updated_at DESC LIMIT %s OFFSET %s""", *p, limit, offset)


async def conversation_detail(conn, conv_id, cid=None):
    wc, p = _w("c", cid)
    conv = await q1(conn, f"""SELECT c.id, c.title, c.exchange_count, c.created_at, u.full_name AS employee, u.email, co.name AS company
        FROM conversations c JOIN users u ON u.id=c.user_id JOIN companies co ON co.id=c.company_id WHERE c.id=%s {wc}""", conv_id, *p)
    if not conv:
        return None
    msgs = await q(conn, """SELECT id, role, exchange_no, content, has_evidence, model_name, latency_ms, created_at
                            FROM messages WHERE conversation_id=%s ORDER BY exchange_no, role""", conv_id)
    ids = [m["id"] for m in msgs if m["role"] == "assistant"]
    fb = await q(conn, """SELECT f.message_id, eq.text AS question, f.rating, f.bool_value FROM feedback f
                          JOIN evaluation_questions eq ON eq.id=f.question_id WHERE f.message_id = ANY(%s::uuid[])""", ids)
    ev = await q(conn, """SELECT rl.message_id, rl.rank, rl.fused_score, rl.used_in_prompt, d.filename
                          FROM retrieval_logs rl LEFT JOIN chunks ch ON ch.id=rl.chunk_id LEFT JOIN documents d ON d.id=ch.document_id
                          WHERE rl.message_id = ANY(%s::uuid[]) ORDER BY rl.rank""", ids)
    for m in msgs:
        m["feedback"] = [f for f in fb if f["message_id"] == m["id"]]
        m["evidence"] = [e for e in ev if e["message_id"] == m["id"]]
    return {**conv, "messages": msgs}


EXPORT_COLUMNS = ["conversation_id", "employee", "email", "exchange_no", "asked_at", "question", "answer", "has_evidence", "score"]


async def conversation_export_rows(conn, cid=None, ids=None):
    wc, p = _w("c", cid)
    if ids:
        wc += " AND c.id = ANY(%s::uuid[])"
        p += (ids,)
    return await q(conn, f"""SELECT c.id AS conversation_id, u.full_name AS employee, u.email, qm.exchange_no,
        qm.created_at AS asked_at, qm.content AS question, am.content AS answer, am.has_evidence,
        (SELECT round(avg(f.rating)::numeric,2) FROM feedback f WHERE f.message_id=am.id) AS score
        FROM conversations c JOIN users u ON u.id=c.user_id
        JOIN messages qm ON qm.conversation_id=c.id AND qm.role='user'
        JOIN messages am ON am.conversation_id=c.id AND am.exchange_no=qm.exchange_no AND am.role='assistant'
        WHERE true {wc} ORDER BY c.created_at, qm.exchange_no""", *p)
