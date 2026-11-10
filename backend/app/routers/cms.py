"""SuperAdmin-managed content stored in the database: landing page, onboarding pages (versioned),
application form fields and supported languages."""
import json
from uuid import UUID

from fastapi import APIRouter, Depends
from psycopg.types.json import Jsonb

from ..db import ex, q, q1
from ..deps import SA
from ..errors import err
from ..rag.ai import get_embedder, get_llm
from ..rag.lang import invalidate_cache, load_detector
from ..schemas import FormFieldIn, LanguageIn, SiteContentIn, StepIn
from ..services.chat import build_user_prompt, language_directive
from ..services.common import audit
from ..services.config_service import get_active, resolve_key

router = APIRouter(prefix="/superadmin", tags=["SuperAdmin - Content & Languages"])


# ------------------------------ landing page ------------------------------
@router.get("/site-content", summary="All landing-page sections")
async def list_site(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, "SELECT key, label, content, position, is_active, updated_at FROM site_content ORDER BY position, key")


@router.put("/site-content/{key}", summary="Edit (or create) a landing-page section")
async def put_site(key: str, body: SiteContentIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    if not key.replace("_", "").isalnum() or len(key) > 50:
        raise err(422, "invalid_key", "Section key must be letters, numbers and underscores.")
    cur = await q1(conn, "SELECT * FROM site_content WHERE key=%s", key)
    content = body.content.model_dump() if body.content is not None else (cur["content"] if cur else {})
    label = body.label or (cur["label"] if cur else key.replace("_", " ").title())
    pos = body.position if body.position is not None else (cur["position"] if cur else 99)
    active = body.is_active if body.is_active is not None else (cur["is_active"] if cur else True)
    row = await q1(conn, """INSERT INTO site_content (key, label, content, position, is_active, updated_by) VALUES (%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (key) DO UPDATE SET label=EXCLUDED.label, content=EXCLUDED.content, position=EXCLUDED.position,
                              is_active=EXCLUDED.is_active, updated_by=EXCLUDED.updated_by, updated_at=now()
                            RETURNING key, label, content, position, is_active, updated_at""", key, label, Jsonb(content), pos, active, user["id"])
    await audit(conn, user["id"], "site_content.update", target_type="site_content", target_id=key)
    return row


@router.delete("/site-content/{key}")
async def delete_site(key: str, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    await ex(conn, "DELETE FROM site_content WHERE key=%s", key)
    await audit(conn, user["id"], "site_content.delete", target_type="site_content", target_id=key)
    return {"ok": True}


# ------------------------------ onboarding steps (versioned) ------------------------------
STEP_SQL = """SELECT s.id, s.key, s.position, s.requires_acceptance, s.is_active, s.current_version_id,
                     v.version, v.title, v.body_markdown, v.created_at AS version_created_at,
                     (SELECT count(*) FROM onboarding_step_versions x WHERE x.step_id = s.id) AS versions,
                     (SELECT count(*) FROM terms_acceptances t JOIN onboarding_step_versions x ON x.id = t.step_version_id WHERE x.step_id = s.id) AS acceptances
              FROM onboarding_steps s LEFT JOIN onboarding_step_versions v ON v.id = s.current_version_id"""


@router.get("/onboarding-steps", summary="Walkthrough pages with their current version")
async def list_steps(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, STEP_SQL + " ORDER BY s.position, s.created_at")


async def _new_version(conn, step_id, title, body, user_id):
    n = (await q1(conn, "SELECT coalesce(max(version),0)+1 AS n FROM onboarding_step_versions WHERE step_id=%s", step_id))["n"]
    v = await q1(conn, "INSERT INTO onboarding_step_versions (step_id, version, title, body_markdown, created_by) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                 step_id, n, title, body, user_id)
    await ex(conn, "UPDATE onboarding_steps SET current_version_id=%s WHERE id=%s", v["id"], step_id)


@router.post("/onboarding-steps", status_code=201, summary="Create a walkthrough page")
async def create_step(body: StepIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    if not (body.key and body.title and body.body_markdown):
        raise err(422, "missing_fields", "key, title and body_markdown are required.")
    s = await q1(conn, "INSERT INTO onboarding_steps (key, position, requires_acceptance) VALUES (%s,%s,%s) RETURNING id",
                 body.key, body.position or 99, bool(body.requires_acceptance))
    await _new_version(conn, s["id"], body.title, body.body_markdown, user["id"])
    await audit(conn, user["id"], "onboarding.step.create", target_type="onboarding_step", target_id=s["id"])
    return await q1(conn, STEP_SQL + " WHERE s.id=%s", s["id"])


@router.put("/onboarding-steps/{step_id}", summary="Edit a page. Changing the title/text publishes a NEW version (old acceptances keep their version)")
async def update_step(step_id: UUID, body: StepIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    cur = await q1(conn, STEP_SQL + " WHERE s.id=%s", step_id)
    if not cur:
        raise err(404, "step_not_found", "Page not found.")
    title = body.title if body.title is not None else cur["title"]
    text = body.body_markdown if body.body_markdown is not None else cur["body_markdown"]
    if title != cur["title"] or text != cur["body_markdown"]:
        await _new_version(conn, step_id, title, text, user["id"])
    for col, val in (("requires_acceptance", body.requires_acceptance), ("position", body.position), ("is_active", body.is_active)):
        if val is not None:
            await ex(conn, f"UPDATE onboarding_steps SET {col}=%s WHERE id=%s", val, step_id)
    await audit(conn, user["id"], "onboarding.step.update", target_type="onboarding_step", target_id=step_id)
    return await q1(conn, STEP_SQL + " WHERE s.id=%s", step_id)


@router.get("/onboarding-steps/{step_id}/versions", summary="Version history of a page")
async def step_versions(step_id: UUID, ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, """SELECT v.id, v.version, v.title, v.body_markdown, v.created_at, u.full_name AS created_by,
                            (SELECT count(*) FROM terms_acceptances t WHERE t.step_version_id = v.id) AS acceptances
                            FROM onboarding_step_versions v LEFT JOIN users u ON u.id = v.created_by
                            WHERE v.step_id=%s ORDER BY v.version DESC""", step_id)


# ------------------------------ application form fields ------------------------------
@router.get("/application-fields", summary="Fields of the company-request form")
async def list_fields(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, "SELECT * FROM application_form_fields ORDER BY position, created_at")


@router.post("/application-fields", status_code=201)
async def add_field(body: FormFieldIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    if not body.key:
        raise err(422, "missing_key", "A field key (letters, numbers, underscore) is required.")
    row = await q1(conn, """INSERT INTO application_form_fields (key, label, help_text, type, options, required, position, is_active)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                   body.key, body.label, body.help_text, body.type, Jsonb([o.strip() for o in body.options if o.strip()]), body.required, body.position, body.is_active)
    await audit(conn, user["id"], "application_field.create", target_id=row["id"])
    return row


@router.put("/application-fields/{field_id}")
async def edit_field(field_id: UUID, body: FormFieldIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    cur = await q1(conn, "SELECT * FROM application_form_fields WHERE id=%s", field_id)
    if not cur:
        raise err(404, "field_not_found", "Field not found.")
    active = True if cur["is_system"] else body.is_active          # system fields stay on
    required = True if cur["is_system"] else body.required
    row = await q1(conn, """UPDATE application_form_fields SET label=%s, help_text=%s, type=%s, options=%s, required=%s, position=%s, is_active=%s
                            WHERE id=%s RETURNING *""", body.label, body.help_text, cur["type"] if cur["is_system"] else body.type,
                   Jsonb([o.strip() for o in body.options if o.strip()]), required, body.position, active, field_id)
    await audit(conn, user["id"], "application_field.update", target_id=field_id)
    return row


@router.delete("/application-fields/{field_id}")
async def delete_field(field_id: UUID, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    cur = await q1(conn, "SELECT is_system FROM application_form_fields WHERE id=%s", field_id)
    if not cur:
        raise err(404, "field_not_found", "Field not found.")
    if cur["is_system"]:
        raise err(409, "system_field", "This field is required by the system and cannot be deleted.")
    await ex(conn, "DELETE FROM application_form_fields WHERE id=%s", field_id)
    await audit(conn, user["id"], "application_field.delete", target_id=field_id)
    return {"ok": True}


# ------------------------------ languages ------------------------------
@router.get("/languages", summary="Supported languages")
async def list_languages(ctx=Depends(SA, scope="function")):
    _, conn = ctx
    return await q(conn, "SELECT * FROM languages ORDER BY position, code")


def _clean_words(words):
    return sorted({w.strip().lower() for w in words if w and w.strip()})


@router.post("/languages", status_code=201, summary="Add a language (e.g. Swahili) as data - no code change")
async def add_language(body: LanguageIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    if not body.code:
        raise err(422, "missing_code", "A 2-3 letter language code (e.g. sw) is required.")
    row = await q1(conn, """INSERT INTO languages (code, name, native_name, is_enabled, stopwords, sample_text, sample_text_en, sample_question, position)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""", body.code, body.name, body.native_name, body.is_enabled,
                   _clean_words(body.stopwords), body.sample_text, body.sample_text_en, body.sample_question, body.position)
    invalidate_cache()
    await audit(conn, user["id"], "language.create", target_id=body.code)
    return row


@router.put("/languages/{code}")
async def edit_language(code: str, body: LanguageIn, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    if not body.is_enabled and (await q1(conn, "SELECT count(*) AS n FROM languages WHERE is_enabled AND code<>%s", code))["n"] == 0:
        raise err(409, "last_language", "At least one language must stay enabled.")
    row = await q1(conn, """UPDATE languages SET name=%s, native_name=%s, is_enabled=%s, stopwords=%s, sample_text=%s, sample_text_en=%s,
                            sample_question=%s, position=%s WHERE code=%s RETURNING *""", body.name, body.native_name, body.is_enabled,
                   _clean_words(body.stopwords), body.sample_text, body.sample_text_en, body.sample_question, body.position, code)
    if not row:
        raise err(404, "language_not_found", "Language not found.")
    invalidate_cache()
    await audit(conn, user["id"], "language.update", target_id=code)
    return row


@router.delete("/languages/{code}")
async def delete_language(code: str, ctx=Depends(SA, scope="function")):
    user, conn = ctx
    if code == "en":
        raise err(409, "protected", "English cannot be deleted.")
    await ex(conn, "DELETE FROM languages WHERE code=%s", code)
    invalidate_cache()
    await audit(conn, user["id"], "language.delete", target_id=code)
    return {"ok": True}


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))      # vectors are normalised


DISTRACTOR_DOC = "The company cafeteria serves lunch until two o'clock."
DISTRACTOR_QUERY = "What time does the cafeteria close?"


@router.post("/languages/check", summary="Test whether the ACTIVE embedding + LLM models really handle each language")
async def language_check(ctx=Depends(SA, scope="function")):
    """Embeds a translation pair and an unrelated sentence, compares cosine similarities (cross-language retrieval),
    and asks the LLM a question in the language over an English passage."""
    _, conn = ctx
    cfg = await get_active(conn)
    langs = await q(conn, """SELECT * FROM languages WHERE is_enabled AND code <> 'en' AND sample_text IS NOT NULL
                             AND sample_text_en IS NOT NULL AND sample_question IS NOT NULL ORDER BY position, code""")
    detector = await load_detector(force=True)
    out = []
    for L in langs:
        res = {"code": L["code"], "name": L["name"]}
        try:
            ekey = await resolve_key(conn, cfg.embedding_cfg.credential_id) if cfg.embedding_cfg.provider == "google" else ""
            emb = get_embedder(cfg.embedding_cfg, ekey)
            d_rw, d_en, d_bad = await emb.embed([L["sample_text"], L["sample_text_en"], DISTRACTOR_DOC], "RETRIEVAL_DOCUMENT")
            q_rw, q_en, q_bad = await emb.embed([L["sample_question"], L["sample_text_en"], DISTRACTOR_QUERY], "RETRIEVAL_QUERY")
            m1, b1 = _cos(q_rw, d_en), _cos(q_rw, d_bad)     # ask in language, document in English
            m2, b2 = _cos(q_en, d_rw), _cos(q_bad, d_rw)     # ask in English, document in the language
            res["embedding"] = {"ok": m1 > b1 and m2 > b2,
                                "ask_in_language_doc_in_english": {"match": round(m1, 3), "unrelated": round(b1, 3)},
                                "ask_in_english_doc_in_language": {"match": round(m2, 3), "unrelated": round(b2, 3)},
                                "suggested_min_score": round((min(m1, m2) + max(b1, b2)) / 2, 2)}
        except Exception as e:
            res["embedding"] = {"ok": False, "error": str(e)[:300]}
        try:
            lkey = await resolve_key(conn, cfg.llm_cfg.credential_id) if cfg.llm_cfg.provider == "google" else ""
            ctxs = [{"filename": "language-check.txt", "page": None, "text": L["sample_text_en"]}]
            r = await get_llm(cfg.llm_cfg, lkey).generate(cfg.prompt_cfg.system_prompt, [],
                                                          build_user_prompt(L["sample_question"], ctxs, language_directive(L["code"], detector.names)))
            det = detector.detect(r.text)
            res["llm"] = {"ok": det == L["code"], "detected_language": det, "answer": r.text[:600],
                          "note": "Please have a native speaker judge the quality of this answer."}
        except Exception as e:
            res["llm"] = {"ok": False, "error": str(e)[:300]}
        out.append(res)
    return {"embedding_model": cfg.embedding_cfg.model, "llm_model": cfg.llm_cfg.model, "languages": out,
            "note": "Compare 'match' with 'unrelated': match must be clearly higher. Set retrieval min_score between them (see suggested_min_score)."}
