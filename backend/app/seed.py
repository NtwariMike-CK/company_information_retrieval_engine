"""Idempotent startup seeding: first SuperAdmin, default RAG config, evaluation questions, languages,
landing page, onboarding pages, request-form fields. Content tables are seeded only when empty."""
import logging

from psycopg.types.json import Jsonb

from .db import ex, q1, tx
from .schemas import (BLOCKS, DEFAULT_NO_EVIDENCE_PROMPT, DEFAULT_SYSTEM_PROMPT, LEGACY_NO_EVIDENCE_PROMPT,
                      LEGACY_SYSTEM_PROMPT, PromptCfg)
from .eval.starter import ensure_starter_dataset
from .security import hash_password
from .seed_content import FORM_FIELDS, LANGUAGES, SITE_CONTENT, STEPS
from .settings import settings

log = logging.getLogger("seed")


async def seed():
    async with tx(bypass=True) as conn:
        await ex(conn, "SELECT pg_advisory_xact_lock(424242)")
        if not await q1(conn, "SELECT 1 FROM users WHERE role='super_admin' LIMIT 1"):
            await ex(conn, "INSERT INTO users (role, full_name, email, password_hash) VALUES ('super_admin', %s, %s, %s)",
                     settings.superadmin_name, settings.superadmin_email, hash_password(settings.superadmin_password))
            log.warning("Created SuperAdmin %s - change the password after first login", settings.superadmin_email)
        if not await q1(conn, "SELECT 1 FROM rag_config_versions LIMIT 1"):
            cols = list(BLOCKS)
            await ex(conn, f"INSERT INTO rag_config_versions ({', '.join(cols)}, status, activated_at) VALUES ({', '.join(['%s'] * len(cols))}, 'active', now())",
                     *[Jsonb(BLOCKS[c]().model_dump(mode="json")) for c in cols])
        else:
            # upgrade ONLY configs that still use the untouched original prompts to the bilingual prompts; customised prompts are never overwritten
            active = await q1(conn, "SELECT id FROM rag_config_versions WHERE status='active' AND prompt_cfg = %s::jsonb",
                              __import__("json").dumps({"system_prompt": LEGACY_SYSTEM_PROMPT, "no_evidence_prompt": LEGACY_NO_EVIDENCE_PROMPT}))
            if active:
                others = [c for c in BLOCKS if c != "prompt_cfg"]
                await ex(conn, "UPDATE rag_config_versions SET status='archived' WHERE id=%s", active["id"])
                await ex(conn, f"""INSERT INTO rag_config_versions ({', '.join(others)}, prompt_cfg, status, activated_at)
                                   SELECT {', '.join(others)}, %s::jsonb, 'active', now() FROM rag_config_versions WHERE id=%s""",
                         __import__("json").dumps(PromptCfg().model_dump()), active["id"])
                log.info("Upgraded default prompts to the bilingual (English/Kinyarwanda) versions")
        if not await q1(conn, "SELECT 1 FROM evaluation_questions LIMIT 1"):
            await ex(conn, "INSERT INTO evaluation_questions (text, type, position) VALUES (%s,'rating_1_5',1), (%s,'true_false',2)",
                     "How helpful was this answer?", "Did the answer fully address your question?")
        if not await q1(conn, "SELECT 1 FROM languages LIMIT 1"):
            for l in LANGUAGES:
                await ex(conn, """INSERT INTO languages (code, name, native_name, stopwords, sample_text, sample_text_en, sample_question, position)
                                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", l["code"], l["name"], l["native_name"], l["stopwords"],
                         l["sample_text"], l["sample_text_en"], l["sample_question"], l["position"])
        if not await q1(conn, "SELECT 1 FROM site_content LIMIT 1"):
            for key, label, pos, content in SITE_CONTENT:
                await ex(conn, "INSERT INTO site_content (key, label, content, position) VALUES (%s,%s,%s,%s)", key, label, Jsonb(content), pos)
        if not await q1(conn, "SELECT 1 FROM onboarding_steps LIMIT 1"):
            for key, pos, req, title, body in STEPS:
                s = await q1(conn, "INSERT INTO onboarding_steps (key, position, requires_acceptance) VALUES (%s,%s,%s) RETURNING id", key, pos, req)
                v = await q1(conn, "INSERT INTO onboarding_step_versions (step_id, version, title, body_markdown) VALUES (%s,1,%s,%s) RETURNING id", s["id"], title, body)
                await ex(conn, "UPDATE onboarding_steps SET current_version_id=%s WHERE id=%s", v["id"], s["id"])
        if not await q1(conn, "SELECT 1 FROM application_form_fields LIMIT 1"):
            for key, label, help_text, typ, opts, req, system, pos in FORM_FIELDS:
                await ex(conn, """INSERT INTO application_form_fields (key, label, help_text, type, options, required, is_system, position)
                                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", key, label, help_text, typ, Jsonb(opts), req, system, pos)
        await ensure_starter_dataset(conn)
