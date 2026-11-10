"""Unit tests for English / Kinyarwanda handling (no database or network). Run:  python tests/test_language.py  (or pytest)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DATABASE_URL", "postgresql://x:y@localhost/z")

from types import SimpleNamespace
from app.rag.chunking import chunk_pages, split_text, attach_headings
from app.rag.clean import clean_pages
from app.rag.lang import Detector
from app.rag.retrieval import or_query
from app.schemas import ChunkingCfg, CleaningCfg
from app.seed_content import LANGUAGES

DET = Detector([{**l, "stopwords": l["stopwords"]} for l in LANGUAGES])
EN = "Employees are entitled to twenty-five days of leave every year, and requests must be approved by the manager."
RW = "Abakozi bose bagomba kubahiriza amategeko y'akazi kandi bakubahana mu kazi."


def test_detects_english_and_kinyarwanda():
    assert DET.detect(EN) == "en"
    assert DET.detect(RW) == "rw"
    assert DET.detect("Abakozi bemerewe iminsi ingahe y'ikiruhuko buri mwaka?") == "rw"
    assert DET.detect("How many vacation days do employees get?") == "en"


def test_unsure_returns_none():
    assert DET.detect("ok") is None
    assert DET.detect("Frw 25000 2026") is None


def test_stopword_sets_do_not_overlap():
    en, rw = [set(l["stopwords"]) for l in LANGUAGES]
    assert not (en & rw), en & rw


def test_chunks_never_mix_languages():
    text = EN + "\n\n" + EN + "\n\n" + RW + "\n\n" + RW
    cfg = ChunkingCfg(strategy="recursive", chunk_size=2000, overlap=0)
    _, children = chunk_pages([(1, text)], cfg, DET)
    langs = [c["lang"] for c in children]
    assert langs == ["en", "rw"], langs
    assert "Abakozi" not in children[0]["content"] and "Employees" not in children[1]["content"]


def test_parent_child_keeps_language_and_page():
    cfg = ChunkingCfg(strategy="parent_child", parent_size=600, child_size=200, overlap=20)
    parents, children = chunk_pages([(3, (EN + " ") * 6 + "\n\n" + (RW + " ") * 6)], cfg, DET)
    assert {p["lang"] for p in parents} == {"en", "rw"}
    assert all(c["page"] == 3 and c["lang"] and c["parent_index"] is not None for c in children)


def test_abbreviations_decimals_and_lists_are_not_split():
    t = "Dr. Smith approved the plan. The budget is 3.5 million. Prof. Mugabo agreed."
    assert split_text(t, 200) == [t]
    pieces = split_text("1. First item here.\n2. Second item here.\n3. Third item here.", 30)
    assert all(p[0].isdigit() for p in pieces if p), pieces


def test_heading_stays_with_its_text():
    assert attach_headings("Leave policy\n\nEmployees get 25 days.") == "Leave policy\nEmployees get 25 days."


def test_apostrophes_are_normalised_for_kinyarwanda():
    pages, stats = clean_pages([(1, "Abakozi b\u2019akazi n\u2019ubwo y\u2018abo")], CleaningCfg(), "txt", DET)
    assert "\u2019" not in pages[0][1] and "b'akazi" in pages[0][1]
    assert "paragraphs_by_language" in stats


def test_query_tokens_are_unicode_safe_and_drop_stopwords():
    q = or_query("Abakozi bemerewe iminsi ingahe y'ikiruhuko buri mwaka? Café", DET.stopwords)
    assert "abakozi" in q and "ikiruhuko" in q and "caf" not in q.split(" | ") and "café" in q.split(" | ")
    assert "buri" not in q.split(" | ") and "y" not in q.split(" | ")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for f in fns:
        try:
            f(); print("PASS", f.__name__)
        except AssertionError as e:
            failed += 1; print("FAIL", f.__name__, "->", e)
    print(f"\n{len(fns) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
