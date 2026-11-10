import json
from uuid import UUID

from psycopg.types.json import Jsonb

from ..db import q, q1, ex
from ..errors import err
from ..rag.ai import AIError, get_embedder, get_llm
from ..schemas import BLOCKS, RagConfig, RagConfigUpdate
from ..security import decrypt_secret

COLUMNS = list(BLOCKS)


def parse_config(row: dict) -> RagConfig:
    return RagConfig(id=row["id"], version=row["version"], **{c: row[c] for c in COLUMNS})


async def get_active(conn) -> RagConfig:
    row = await q1(conn, "SELECT * FROM rag_config_versions WHERE status = 'active'")
    if not row:
        raise err(503, "no_active_config", "No active RAG configuration exists.")
    return parse_config(row)


async def resolve_key(conn, credential_id: UUID | None) -> str:
    """Decrypt the API key for a credential; falls back to the newest active credential."""
    if credential_id:
        row = await q1(conn, "SELECT encrypted_key FROM api_credentials WHERE id=%s AND is_active", credential_id)
    else:
        row = await q1(conn, "SELECT encrypted_key FROM api_credentials WHERE is_active ORDER BY created_at DESC LIMIT 1")
    if not row:
        raise AIError("no active API credential is configured")
    return decrypt_secret(row["encrypted_key"])


async def create_draft(conn, update: RagConfigUpdate, user_id) -> UUID:
    active = await get_active(conn)
    merged = {}
    for col in COLUMNS:
        new = getattr(update, col)
        merged[col] = (new if new is not None else getattr(active, col)).model_dump(mode="json")
    cols = ", ".join(COLUMNS)
    ph = ", ".join(["%s"] * len(COLUMNS))
    row = await q1(conn, f"INSERT INTO rag_config_versions ({cols}, status, created_by) VALUES ({ph}, 'draft', %s) RETURNING id",
                   *[Jsonb(merged[c]) for c in COLUMNS], user_id)
    return row["id"]


async def live_validate(conn, cfg: RagConfig) -> dict:
    """Real test calls so a broken key / wrong model name never becomes the active config."""
    report = {"embedding": {"ok": False}, "llm": {"ok": False}}
    try:
        key = await resolve_key(conn, cfg.embedding_cfg.credential_id) if cfg.embedding_cfg.provider == "google" else ""
        vec = (await get_embedder(cfg.embedding_cfg, key).embed(["configuration test"], "RETRIEVAL_QUERY"))[0]
        if len(vec) != cfg.embedding_cfg.dimensions:
            raise AIError(f"model returned {len(vec)} dimensions, expected {cfg.embedding_cfg.dimensions}")
        report["embedding"] = {"ok": True, "dimensions": len(vec)}
    except Exception as e:
        report["embedding"] = {"ok": False, "error": str(e)[:300]}
    try:
        key = await resolve_key(conn, cfg.llm_cfg.credential_id) if cfg.llm_cfg.provider == "google" else ""
        res = await get_llm(cfg.llm_cfg, key).generate("You are a test.", [], "Reply with the single word OK.")
        report["llm"] = {"ok": bool(res.text)}
    except Exception as e:
        report["llm"] = {"ok": False, "error": str(e)[:300]}
    report["ok"] = report["embedding"]["ok"] and report["llm"]["ok"]
    return report
