"""Workbook sheet 2_Unit, rows U1-U14. No database, no network, ZERO Gemini calls (safe to run on the real stack).
Run:  pytest tests/test_workbook_unit.py -v --cov=app --cov-report=term | tee ../docs/testing/real_run/unit_output.txt
Each test name starts with the workbook ID (U1 ... U14)."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DATABASE_URL", "postgresql://x:y@localhost/z")

from types import SimpleNamespace
import pytest

from app.rag import retrieval
from app.rag.ai import FakeEmbedder
from app.rag.chunking import chunk_pages
from app.rag.clean import clean_pages
from app.rag.retrieval import followup_concat, rrf_fuse
from app.schemas import ChunkingCfg, CleaningCfg, RetrievalCfg
from app.services.chat import build_user_prompt
from app.services.ingest import batched

# Workbook parameters: parent 600, child 200, overlap 20
CFG = ChunkingCfg(strategy="parent_child", parent_size=600, child_size=200, overlap=20, language_aware=False)
SAMPLE = ("Annual leave policy. " + "Every employee is entitled to paid leave after the probation period ends. " * 60)


def _chunks(text=SAMPLE):
    return chunk_pages([(1, text)], CFG)


def test_U1_parent_chunks_at_most_600():
    parents, _ = _chunks()
    assert len(parents) > 1 and all(len(p["content"]) <= 600 for p in parents)


def test_U2_child_chunks_at_most_200():
    _, children = _chunks()
    assert len(children) > 1 and all(len(c["content"]) <= 200 for c in children)


def test_U3_consecutive_children_overlap_by_20():
    # long unbroken text forces hard splits, where overlap is applied exactly
    _, children = chunk_pages([(1, "abcdefghij" * 100)], ChunkingCfg(strategy="fixed", chunk_size=200, overlap=20, language_aware=False))
    pairs = [(a["content"], b["content"]) for a, b in zip(children, children[1:])]
    assert pairs and all(a[-20:] == b[:20] for a, b in pairs)


def test_U4_every_child_points_to_its_parent():
    parents, children = _chunks()
    idx = {p["index"]: p["content"] for p in parents}
    assert all(c["parent_index"] in idx for c in children)
    assert all(c["content"].strip()[-30:] in idx[c["parent_index"]] for c in children)   # the end of each child lies inside its parent


@pytest.mark.parametrize("text", ["", "   ", "Short."])
def test_U5_empty_or_very_short_document(text):
    parents, children = _chunks(text)
    assert len(children) <= 1 and len(parents) <= 1


def test_U6_cleaning_matches_expected_sample():
    cfg = CleaningCfg()
    raw = [(i, f"ACME CONFIDENTIAL\nLeave for {w} is in the employ-\nee handbook  for  {w}.\nPage {i} of 3") for i, w in ((1, "staff"), (2, "interns"), (3, "managers"))]
    out, _ = clean_pages(raw, cfg, "pdf")
    assert [t for _, t in out] == [f"Leave for {w} is in the employee handbook for {w}." for w in ("staff", "interns", "managers")]


def test_U7_51_chunks_make_two_batches_50_and_1():
    assert [len(b) for b in batched(list(range(51)), 50)] == [50, 1]


def test_U8_vectors_have_768_values():
    vecs = asyncio.run(FakeEmbedder(768).embed(["one", "two"], "RETRIEVAL_DOCUMENT")) if hasattr(FakeEmbedder, "embed") else []
    assert vecs and all(len(v) == 768 for v in vecs)


def test_U9_rrf_matches_hand_calculation():
    dense = [{"id": "A", "parent_id": None, "score": .9}, {"id": "B", "parent_id": None, "score": .8}]
    sparse = [{"id": "B", "parent_id": None, "score": 5}, {"id": "C", "parent_id": None, "score": 4}]
    out = {c["id"]: c["fused_score"] for c in rrf_fuse(dense, sparse, 60)}
    assert out["A"] == pytest.approx(1 / 61) and out["B"] == pytest.approx(1 / 62 + 1 / 61) and out["C"] == pytest.approx(1 / 62)
    assert [c["id"] for c in rrf_fuse(dense, sparse, 60)] == ["B", "A", "C"]


def test_U10_chunk_in_both_lists_ranks_higher():
    dense = [{"id": "only_dense", "parent_id": None, "score": .9}, {"id": "both", "parent_id": None, "score": .8}]
    sparse = [{"id": "both", "parent_id": None, "score": 3}]
    assert rrf_fuse(dense, sparse, 60)[0]["id"] == "both"


def _run_retrieve(best_score, final_k=6, n=3):
    async def fake_dense(*a, **k):
        return [{"id": f"c{i}", "parent_id": None, "score": best_score - i * .01} for i in range(n)]
    async def fake_sparse(*a, **k):
        return []
    orig = retrieval.dense_search, retrieval.sparse_search
    retrieval.dense_search, retrieval.sparse_search = fake_dense, fake_sparse
    try:
        cfg = RetrievalCfg(min_score=0.25, final_k=final_k)
        return asyncio.run(retrieval.retrieve(None, "c", "q", [0.1], cfg, "m"))
    finally:
        retrieval.dense_search, retrieval.sparse_search = orig


def test_U11_threshold_025_024_no_data_026_passes():
    assert _run_retrieve(0.24)[1] is False
    assert _run_retrieve(0.26)[1] is True


def test_U12_no_data_path_uses_no_context_prompt():
    _, has_evidence = _run_retrieve(0.10)
    assert has_evidence is False
    assert "No relevant context was found" in build_user_prompt("What is the dress code?", [])
    # the question being logged and shown in Analytics is covered by api_checks.py (U17)


def test_U13_eight_candidates_four_allowed():
    fused, _ = _run_retrieve(0.9, final_k=4, n=8)
    assert len(fused) == 4


def test_U14_followup_is_completed_with_previous_question():
    hist = [{"role": "user", "content": "How many days of annual leave do staff get?"}, {"role": "assistant", "content": "21 days."}]
    out = followup_concat("and for contractors?", hist)
    assert "annual leave" in out and "contractors" in out
