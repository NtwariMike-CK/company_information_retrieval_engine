"""Unit tests for the evaluation metrics: every expected value below is computed by hand. Run: python tests/test_eval_metrics.py"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.eval import metrics as M


def close(a, b, tol=1e-9):
    return abs(a - b) < tol


def test_ranking_metrics_hand_computed():
    rels = [False, True, False, True, False]            # relevant at ranks 2 and 4, total relevant = 2
    assert M.hit_at_k(rels, 1) == 0.0 and M.hit_at_k(rels, 2) == 1.0
    assert close(M.precision_at_k(rels, 5), 2 / 5) and close(M.precision_at_k(rels, 2), 1 / 2)
    assert close(M.recall_at_k(rels, 3, 2), 1 / 2) and close(M.recall_at_k(rels, 5, 2), 1.0)
    assert close(M.reciprocal_rank(rels), 1 / 2)
    assert close(M.average_precision(rels, 2), (1 / 2 + 2 / 4) / 2)                   # (P@2 + P@4) / 2 = 0.5
    dcg = 1 / math.log2(3) + 1 / math.log2(5)
    ideal = 1 / math.log2(2) + 1 / math.log2(3)
    assert close(M.ndcg_at_k(rels, 5, 2), dcg / ideal)


def test_perfect_and_empty_rankings():
    perfect = [True, False, False]
    m = M.rank_metrics(perfect, 1)
    assert m["hit@1"] == 1 and m["mrr"] == 1 and close(m["ndcg@10"], 1.0) and close(m["map"], 1.0)
    none = M.rank_metrics([False] * 10, 3)
    assert none["hit@10"] == 0 and none["mrr"] == 0 and none["ndcg@10"] == 0 and none["map"] == 0


def test_token_f1():
    assert close(M.token_f1("twenty five days", "twenty five days"), 1.0)
    assert M.token_f1("completely different words", "twenty five days") == 0.0
    # prediction 4 tokens, reference 3 tokens, 2 shared -> P=0.5, R=2/3, F1=4/7
    assert close(M.token_f1("you get twenty days", "twenty five days"), 2 * 0.5 * (2 / 3) / (0.5 + 2 / 3))


def test_key_fact_recall_with_alternatives():
    assert M.key_fact_recall("Employees get 25 days of leave.", ["25|twenty-five"]) == 1.0
    assert M.key_fact_recall("They get twenty-five days.", ["25|twenty-five", "manager"]) == 0.5
    assert M.key_fact_recall("anything", []) is None
    assert M.key_fact_recall("Abakozi bemerewe iminsi makumyabiri n'itanu", ["makumyabiri n'itanu"]) == 1.0


def test_evidence_matching_is_tolerant_but_not_loose():
    ev = "Employees are entitled to twenty-five days of paid annual leave per year"
    assert M.phrase_in(ev, "Employees are entitled to twenty-five days of paid annual leave per year. Requests...")
    assert M.phrase_in(ev, "employees ARE entitled to twenty five days of paid annual leave per year")      # case + hyphen
    assert not M.phrase_in("probation period is three months", "probation is a long period of three weeks")  # short phrase: exact only
    assert M.phrase_in("Igihe cy'igeragezwa ni amezi atatu", "## Igihe cy’igeragezwa ni amezi atatu.")        # curly apostrophe
    assert M.evidence_fraction(["alpha beta", "gamma delta"], "alpha beta only") == 0.5


def test_abstention_detection_both_languages():
    assert M.looks_like_abstention("I could not find this in the company documents.")
    assert M.looks_like_abstention("Sinabashije kubona ibisubizo muri dosiye z'ikigo.")
    assert not M.looks_like_abstention("Employees get twenty-five days of leave.")


def test_wilson_interval_properties():
    lo, hi = M.wilson_interval(8, 10)
    assert 0.49 < lo < 0.50 and 0.94 < hi < 0.96                 # known value: 8/10 -> about [0.49, 0.94]
    assert M.wilson_interval(0, 0) == (0.0, 0.0)
    lo0, hi0 = M.wilson_interval(0, 5)
    assert lo0 == 0.0 and hi0 > 0.3
    assert M.wilson_interval(50, 100)[1] - M.wilson_interval(50, 100)[0] < M.wilson_interval(5, 10)[1] - M.wilson_interval(5, 10)[0]


def test_threshold_sweep_and_best_threshold():
    pos, neg = [0.9, 0.8, 0.75, 0.6], [0.4, 0.3, 0.55]          # perfectly separable between 0.55 and 0.6
    curve = M.threshold_sweep(pos, neg, step=0.05)
    at = {round(c["threshold"], 2): c for c in curve}
    assert at[0.0]["recall"] == 1.0 and at[0.0]["precision"] == 4 / 7
    assert at[1.0]["recall"] == 0.0
    best = M.best_threshold(curve)
    assert best["f1"] == 1.0 and 0.55 < best["threshold"] <= 0.6
    c = M.confusion_metrics(tp=3, fp=1, fn=1, tn=5)
    assert close(c["precision"], 0.75) and close(c["recall"], 0.75) and close(c["f1"], 0.75) and close(c["accuracy"], 0.8)


def test_percentile_and_mean():
    assert M.percentile([1, 2, 3, 4, 5], 50) == 3 and M.percentile([], 50) is None
    assert M.mean([1, None, 3]) == 2 and M.mean([None]) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for f in fns:
        try:
            f(); print("PASS", f.__name__)
        except AssertionError as e:
            failed += 1; print("FAIL", f.__name__, "->", repr(e))
    print(f"\n{len(fns) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
