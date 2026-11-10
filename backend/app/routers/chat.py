from uuid import UUID

from fastapi import APIRouter, Depends

from ..db import ex, q, q1
from ..deps import EMP, EMP_USER
from ..errors import err
from ..schemas import AskIn, FeedbackIn, ReportIn
from ..services.chat import ask
from ..services.config_service import get_active

router = APIRouter(prefix="/chat", tags=["Employee Chat"])


@router.get("/status", summary="Is the assistant available? + chat limit")
async def status(ctx=Depends(EMP, scope="function")):
    user, conn = ctx
    c = await q1(conn, "SELECT chatbot_state FROM companies WHERE id=%s", user["company_id"])
    cfg = await get_active(conn)
    return {"chatbot_state": c["chatbot_state"], "available": c["chatbot_state"] == "started",
            "max_exchanges": cfg.chat_cfg.max_exchanges}


@router.get("/conversations", summary="Chat history (sidebar)")
async def list_conversations(ctx=Depends(EMP, scope="function")):
    user, conn = ctx
    return await q(conn, "SELECT id, title, exchange_count, created_at, updated_at FROM conversations WHERE user_id=%s ORDER BY updated_at DESC LIMIT 200", user["id"])


@router.post("/conversations", status_code=201, summary="New chat")
async def new_conversation(ctx=Depends(EMP, scope="function")):
    user, conn = ctx
    return await q1(conn, "INSERT INTO conversations (company_id, user_id) VALUES (%s,%s) RETURNING id, title, exchange_count, created_at", user["company_id"], user["id"])


@router.get("/conversations/{conv_id}", summary="Open a previous chat")
async def get_conversation(conv_id: UUID, ctx=Depends(EMP, scope="function")):
    user, conn = ctx
    conv = await q1(conn, "SELECT id, title, exchange_count, created_at FROM conversations WHERE id=%s AND user_id=%s", conv_id, user["id"])
    if not conv:
        raise err(404, "conversation_not_found", "Conversation not found.")
    msgs = await q(conn, """SELECT m.id, m.role, m.exchange_no, m.content, m.has_evidence, m.created_at,
                            EXISTS (SELECT 1 FROM feedback f WHERE f.message_id=m.id) AS rated
                            FROM messages m WHERE m.conversation_id=%s ORDER BY m.exchange_no, m.role""", conv_id)
    cfg = await get_active(conn)
    return {**conv, "messages": msgs, "remaining_exchanges": cfg.chat_cfg.max_exchanges - conv["exchange_count"]}


@router.post("/conversations/{conv_id}/messages", summary="Ask a question / follow-up (RAG answer)")
async def ask_question(conv_id: UUID, body: AskIn, user: dict = Depends(EMP_USER)):
    # no pooled connection is held here: ask() opens short transactions around the (slow) AI calls
    return await ask(user, conv_id, body.question.strip())


@router.post("/messages/{message_id}/feedback", summary="Rate an answer when prompted")
async def submit_feedback(message_id: UUID, body: FeedbackIn, ctx=Depends(EMP, scope="function")):
    user, conn = ctx
    msg = await q1(conn, """SELECT m.id FROM messages m JOIN conversations c ON c.id=m.conversation_id
                            WHERE m.id=%s AND m.role='assistant' AND c.user_id=%s""", message_id, user["id"])
    if not msg:
        raise err(404, "message_not_found", "Message not found.")
    for a in body.answers:
        eq = await q1(conn, "SELECT type FROM evaluation_questions WHERE id=%s AND is_active", a.question_id)
        if not eq:
            raise err(404, "question_not_found", "Evaluation question not found.")
        if eq["type"] == "rating_1_5" and (a.rating is None or a.bool_value is not None):
            raise err(422, "invalid_answer", "This question needs a rating from 1 to 5.")
        if eq["type"] == "true_false" and (a.bool_value is None or a.rating is not None):
            raise err(422, "invalid_answer", "This question needs a True/False answer.")
        await ex(conn, """INSERT INTO feedback (company_id, user_id, message_id, question_id, rating, bool_value)
                          VALUES (%s,%s,%s,%s,%s,%s)
                          ON CONFLICT (message_id, question_id, user_id) DO UPDATE SET rating=EXCLUDED.rating, bool_value=EXCLUDED.bool_value""",
                 user["company_id"], user["id"], message_id, a.question_id, a.rating, a.bool_value)
    return {"ok": True}


@router.post("/reports", status_code=201, summary="Report an issue / send a recommendation")
async def create_report(body: ReportIn, ctx=Depends(EMP, scope="function")):
    user, conn = ctx
    if body.conversation_id and not await q1(conn, "SELECT 1 FROM conversations WHERE id=%s AND user_id=%s", body.conversation_id, user["id"]):
        raise err(404, "conversation_not_found", "Conversation not found.")
    if body.message_id and not await q1(conn, "SELECT 1 FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=%s AND c.user_id=%s", body.message_id, user["id"]):
        raise err(404, "message_not_found", "Message not found.")
    return await q1(conn, """INSERT INTO reports (company_id, user_id, conversation_id, message_id, type, comments)
                             VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, type, status, created_at""",
                    user["company_id"], user["id"], body.conversation_id, body.message_id, body.type, body.comments)


@router.get("/reports", summary="My submitted reports")
async def my_reports(ctx=Depends(EMP, scope="function")):
    user, conn = ctx
    return await q(conn, "SELECT id, type, comments, status, created_at FROM reports WHERE user_id=%s ORDER BY created_at DESC", user["id"])
