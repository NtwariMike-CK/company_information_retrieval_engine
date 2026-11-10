"""Pure evaluation metrics (no database, no network) so every formula can be unit-tested.

Retrieval (ranked list of booleans `rels`, True = the chunk contains the ground-truth evidence):
    hit@k, precision@k, recall@k, MRR, nDCG@k, average precision.
Answer quality: token F1, key-fact recall, abstention detection.
Other: evidence matching, Wilson confidence interval, threshold sweep for the "no answer" decision."""
import math
import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
APOSTROPHES = "\u2019\u2018\u02bc\u00b4`"
ABSTENTION_PHRASES = (
    "could not find", "couldn't find", "cannot find", "can't find", "unable to find", "not find", "no information", "does not contain",
    "do not contain", "not available", "do not have information", "don't have information", "not mentioned", "documents do not",
    "sinabashije", "sinabonye", "ntabwo nabashije", "nta makuru", "ntibigaragara",
)


# ----------------------------------------------------------------------------- text helpers
def normalize(text: str) -> str:
    """Lower-case, unify apostrophes, drop punctuation, collapse spaces (works for English and Kinyarwanda)."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    for a in APOSTROPHES + "'":
        t = t.replace(a, " ")
    return " ".join(_PUNCT.sub(" ", t).split())


def tokens(text: str) -> list[str]:
    return normalize(text).split()


def phrase_in(phrase: str, text: str, threshold: float = 0.85, min_fuzzy_tokens: int = 5) -> bool:
    """Does `text` contain the evidence `phrase`? Exact (normalised) substring, or for phrases of at least
    `min_fuzzy_tokens` words, at least `threshold` of the phrase's words (tolerates chunk overlap / formatting)."""
    p, t = normalize(phrase), normalize(text)
    if not p:
        return False
    if p in t:
        return True
    pt = set(p.split())
    return len(pt) >= min_fuzzy_tokens and len(pt & set(t.split())) / len(pt) >= threshold


def evidence_fraction(evidence: list[str], text: str) -> float:
    ev = [e for e in evidence if e and e.strip()]
    return sum(phrase_in(e, text) for e in ev) / len(ev) if ev else 0.0


def looks_like_abstention(answer: str) -> bool:
    a = (answer or "").lower()
    for c in APOSTROPHES:
        a = a.replace(c, "'")
    return any(p in a for p in ABSTENTION_PHRASES)


# ----------------------------------------------------------------------------- ranking metrics
def hit_at_k(rels: list[bool], k: int) -> float:
    return float(any(rels[:k]))


def precision_at_k(rels: list[bool], k: int) -> float:
    return sum(rels[:k]) / k


def recall_at_k(rels: list[bool], k: int, total_relevant: int) -> float:
    return min(sum(rels[:k]), total_relevant) / total_relevant if total_relevant else 0.0


def reciprocal_rank(rels: list[bool]) -> float:
    for i, r in enumerate(rels, 1):
        if r:
            return 1.0 / i
    return 0.0


def ndcg_at_k(rels: list[bool], k: int, total_relevant: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, r in enumerate(rels[:k], 1) if r)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, total_relevant) + 1))
    return dcg / ideal if ideal else 0.0


def average_precision(rels: list[bool], total_relevant: int) -> float:
    hits, s = 0, 0.0
    for i, r in enumerate(rels, 1):
        if r:
            hits += 1
            s += hits / i
    return s / total_relevant if total_relevant else 0.0


def rank_metrics(rels: list[bool], total_relevant: int) -> dict:
    """All ranking metrics for one query (the list is the top-10 ranking)."""
    return {"hit@1": hit_at_k(rels, 1), "hit@3": hit_at_k(rels, 3), "hit@5": hit_at_k(rels, 5), "hit@10": hit_at_k(rels, 10),
            "precision@1": precision_at_k(rels, 1), "precision@3": precision_at_k(rels, 3), "precision@5": precision_at_k(rels, 5),
            "recall@5": recall_at_k(rels, 5, total_relevant), "recall@10": recall_at_k(rels, 10, total_relevant),
            "mrr": reciprocal_rank(rels), "ndcg@10": ndcg_at_k(rels, 10, total_relevant), "map": average_precision(rels, total_relevant)}


# ----------------------------------------------------------------------------- answer metrics
def token_f1(prediction: str, reference: str) -> float:
    """SQuAD-style F1 over normalised word tokens."""
    p, g = tokens(prediction), tokens(reference)
    if not p or not g:
        return float(p == g)
    common = {}
    for w in set(p) & set(g):
        common[w] = min(p.count(w), g.count(w))
    same = sum(common.values())
    if same == 0:
        return 0.0
    precision, recall = same / len(p), same / len(g)
    return 2 * precision * recall / (precision + recall)


def key_fact_recall(answer: str, key_facts: list[str]) -> float | None:
    """Share of required facts present in the answer. A fact may list alternatives separated by '|'."""
    facts = [f for f in key_facts if f and f.strip()]
    if not facts:
        return None
    found = sum(any(phrase_in(alt, answer, min_fuzzy_tokens=99) for alt in f.split("|") if alt.strip()) for f in facts)
    return found / len(facts)


# ----------------------------------------------------------------------------- statistics
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def wilson_interval(successes: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion (better than the normal approximation for small samples)."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def confusion_metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    total = tp + fp + fn + tn
    return {"precision": precision, "recall": recall, "f1": f1, "accuracy": (tp + tn) / total if total else 0.0, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def threshold_sweep(pos_scores: list[float], neg_scores: list[float], step: float = 0.02) -> list[dict]:
    """'Does the knowledge base contain the answer?' decided by: best similarity >= t.
    Positive class = answerable question. Returns precision / recall / F1 / accuracy for every t."""
    curve, n = [], int(round(1 / step))
    for i in range(n + 1):
        t = round(i * step, 4)
        tp = sum(s >= t for s in pos_scores)
        fp = sum(s >= t for s in neg_scores)
        curve.append({"threshold": t, **confusion_metrics(tp, fp, len(pos_scores) - tp, len(neg_scores) - fp)})
    return curve


def best_threshold(curve: list[dict]) -> dict:
    """Threshold with the highest F1; if several tie, the middle of the plateau (the most robust choice)."""
    best = max(c["f1"] for c in curve)
    plateau = [c for c in curve if abs(c["f1"] - best) < 1e-9]
    return plateau[len(plateau) // 2]
