"""Unit tests (no database, no network): security primitives, text cleaning, extraction, fusion, query handling, test embedder.
Run:  pytest tests/test_security_and_pipeline.py -v"""
import asyncio, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DATABASE_URL", "postgresql://x:y@localhost/z")

from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from app import security
from app.rag.ai import FakeEmbedder, v2_prefix
from app.rag.chunking import fixed_split, split_text
from app.rag.clean import clean_pages
from app.rag.extract import ExtractionError, extract_pages
from app.rag.retrieval import followup_concat, or_query, rrf_fuse, vec_literal
from app.schemas import ChatCfg, ChunkingCfg, EmbeddingCfg, LLMCfg


# ------------------------------------------------------------------ security
def test_password_hash_is_salted_and_verifies():
    h1, h2 = security.hash_password("Correct-Horse-1"), security.hash_password("Correct-Horse-1")
    assert h1 != h2 and h1.startswith("$argon2")           # random salt, Argon2 format
    assert security.verify_password(h1, "Correct-Horse-1")
    assert not security.verify_password(h1, "wrong")
    assert not security.verify_password("not-a-hash", "x")  # malformed hash never raises


def test_jwt_round_trip_and_claims():
    t = security.create_token("u-1", "company_admin", "c-1", impersonator="sa-1")
    c = security.decode_token(t)
    assert (c["sub"], c["role"], c["cid"], c["imp"]) == ("u-1", "company_admin", "c-1", "sa-1")


def test_jwt_tampered_and_expired_are_rejected():
    t = security.create_token("u-1", "employee", "c-1")
    with pytest.raises(HTTPException) as e:
        security.decode_token(t[:-3] + "abc")
    assert e.value.status_code == 401 and e.value.detail["code"] == "invalid_token"
    old = security.create_token("u-1", "employee", "c-1", minutes=-1)
    with pytest.raises(HTTPException) as e:
        security.decode_token(old)
    assert e.value.detail["code"] == "token_expired"


def test_api_keys_encrypted_at_rest_round_trip():
    blob = security.encrypt_secret("AIzaSy-secret-key")
    assert b"AIzaSy" not in blob                            # ciphertext does not contain the key
    assert security.decrypt_secret(blob) == "AIzaSy-secret-key"
    assert security.decrypt_secret(memoryview(blob)) == "AIzaSy-secret-key"   # psycopg returns memoryview for bytea


def test_production_refuses_weak_secrets(monkeypatch):
    s = security.settings
    monkeypatch.setattr(s, "environment", "production")
    monkeypatch.setattr(s, "jwt_secret", security.DEV_JWT)
    with pytest.raises(RuntimeError):
        security.assert_production_safe()
    monkeypatch.setattr(s, "jwt_secret", "x" * 40)
    monkeypatch.setattr(s, "secrets_encryption_key", "")
    with pytest.raises(RuntimeError):
        security.assert_production_safe()
    monkeypatch.setattr(s, "secrets_encryption_key", "k")
    security.assert_production_safe()                       # strong settings pass


# ------------------------------------------------------------------ cleaning
CLEAN = SimpleNamespace(normalize_unicode=True, fix_hyphenation=True, merge_soft_wraps=True, remove_headers_footers=True,
                        collapse_whitespace=True, drop_duplicate_paragraphs=False)


def test_cleaning_removes_repeated_headers_and_page_numbers():
    pages = [(i, f"ACME CONFIDENTIAL\nSection {i} body text about leave.\nPage {i} of 4") for i in range(1, 5)]
    out, eda = clean_pages(pages, CLEAN, "pdf")
    assert all("CONFIDENTIAL" not in t and "Page" not in t for _, t in out)
    assert eda["header_footer_lines_removed"] >= 8 and eda["pages"] == 4


def test_cleaning_fixes_hyphenation_soft_wraps_and_whitespace():
    out, _ = clean_pages([(1, "The employ-\nee handbook  says\nleave   is   paid.")], CLEAN, "pdf")
    assert out[0][1] == "The employee handbook says leave is paid."


def test_cleaning_normalises_curly_apostrophes_and_control_chars():
    out, _ = clean_pages([(1, "y’abo n‘ubwo\x00 ok")], CLEAN, "txt")
    assert out[0][1] == "y'abo n'ubwo ok"


def test_duplicate_paragraphs_measured_and_optionally_dropped():
    para = "This paragraph is long enough to count as a duplicate candidate for the report."
    pages = [(1, para + "\n\nUnique ending here.\n\n" + para)]
    _, eda = clean_pages(pages, CLEAN, "txt")
    assert eda["duplicate_paragraph_ratio"] == 0.5
    drop = SimpleNamespace(**{**CLEAN.__dict__, "drop_duplicate_paragraphs": True})
    out, _ = clean_pages(pages, drop, "txt")
    assert out[0][1].count("long enough") == 1


# ------------------------------------------------------------------ extraction
def test_extract_text_markdown_and_errors(tmp_path):
    f = tmp_path / "a.md"; f.write_text("# Title\n\nSome policy text that is long enough.", encoding="utf-8")
    assert extract_pages(str(f), "md")[0][0] == 1
    empty = tmp_path / "e.txt"; empty.write_text("  ", encoding="utf-8")
    with pytest.raises(ExtractionError):
        extract_pages(str(empty), "txt")
    with pytest.raises(ExtractionError):
        extract_pages(str(f), "exe")


def test_extract_docx_reads_paragraphs_and_tables(tmp_path):
    from docx import Document
    d = Document(); d.add_paragraph("Leave policy for all employees.")
    t = d.add_table(rows=1, cols=2); t.rows[0].cells[0].text = "Annual"; t.rows[0].cells[1].text = "25 days"
    p = tmp_path / "x.docx"; d.save(p)
    text = extract_pages(str(p), "docx")[0][1]
    assert "Leave policy" in text and "Annual | 25 days" in text


def test_corrupt_pdf_raises(tmp_path):
    p = tmp_path / "bad.pdf"; p.write_bytes(b"%PDF-1.4 not a pdf")
    with pytest.raises(Exception):
        extract_pages(str(p), "pdf")


# ------------------------------------------------------------------ chunking helpers
def test_split_text_respects_size_and_loses_no_words():
    text = " ".join(f"word{i}" for i in range(400))
    parts = split_text(text, 200, 0)
    assert all(len(p) <= 200 for p in parts)
    assert " ".join(parts).split() == text.split()


def test_fixed_split_overlap():
    parts = fixed_split("abcdefghij" * 10, 30, 10)
    assert parts[0][-10:] == parts[1][:10]


# ------------------------------------------------------------------ retrieval logic
def test_rrf_rewards_agreement_between_dense_and_sparse():
    dense = [{"id": "a", "parent_id": None, "score": .9}, {"id": "b", "parent_id": None, "score": .8}]
    sparse = [{"id": "b", "parent_id": None, "score": 3.0}, {"id": "c", "parent_id": None, "score": 1.0}]
    fused = rrf_fuse(dense, sparse, 60)
    assert fused[0]["id"] == "b"                                           # found by both lists
    assert fused[0]["fused_score"] == pytest.approx(1 / 62 + 1 / 61)
    assert {f["id"] for f in fused} == {"a", "b", "c"}
    assert next(f for f in fused if f["id"] == "c")["dense_score"] is None  # missing score stays None


def test_followup_concat_only_for_short_followups():
    hist = [{"role": "user", "content": "What is the leave policy?"}, {"role": "assistant", "content": "25 days"}]
    assert followup_concat("and for contractors?", hist) == "What is the leave policy? and for contractors?"
    long_q = "Please explain in detail how the travel reimbursement process works for international trips"
    assert followup_concat(long_q, hist) == long_q
    assert followup_concat("and for contractors?", []) == "and for contractors?"


def test_or_query_dedupes_and_caps_terms():
    assert or_query("The the leave leave policy?") == "leave | policy"
    assert or_query("???") == ""
    assert len(or_query(" ".join(f"term{i}" for i in range(80))).split(" | ")) == 30


def test_vector_literal_format():
    assert vec_literal([0.5, -1.0]) == "[0.500000,-1.000000]"


# ------------------------------------------------------------------ test embedder + prefixes + config validation
def test_fake_embedder_is_deterministic_unit_length_and_lexical():
    emb = FakeEmbedder(64)
    a, b, c = asyncio.run(emb.embed(["annual leave policy", "annual leave policy", "cafeteria menu today"], "RETRIEVAL_DOCUMENT"))
    assert a == b
    assert sum(x * x for x in a) == pytest.approx(1.0)
    cos = lambda u, v: sum(x * y for x, y in zip(u, v))
    assert cos(a, a) > cos(a, c)


def test_gemini_embedding_2_task_prefixes():
    assert v2_prefix("hello", "RETRIEVAL_DOCUMENT") == "title: none | text: hello"
    assert v2_prefix("hello", "RETRIEVAL_QUERY") == "task: question answering | query: hello"


def test_config_blocks_validate_ranges():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ChatCfg(max_exchanges=10)                                          # spec: at most 9 exchanges
    with pytest.raises(ValidationError):
        LLMCfg(temperature=3)
    with pytest.raises(ValidationError):
        ChunkingCfg(parent_size=100)
    assert EmbeddingCfg().model == "gemini-embedding-2" and EmbeddingCfg().dimensions == 768
