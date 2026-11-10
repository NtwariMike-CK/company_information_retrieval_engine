"""Language detection for English / Kinyarwanda (and any language added in the `languages` table).
Heuristic: share of common function words (stopwords) per language, loaded from the database so new
languages are data, not code. Returns None when unsure; callers then fall back to 'same language as the question'."""
import re, time

from ..db import q, tx

TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_cache: dict = {"t": 0.0, "det": None}


class Detector:
    def __init__(self, langs: list[dict]):
        self.langs = [(l["code"], {w.lower() for w in (l["stopwords"] or [])}) for l in langs]
        self.names = {l["code"]: l["name"] for l in langs}
        self.stopwords: set[str] = set().union(*[s for _, s in self.langs]) if self.langs else set()

    def scores(self, text: str) -> dict[str, float]:
        toks = [t.lower() for t in TOKEN.findall(text)]
        if not toks:
            return {}
        return {code: sum(1 for t in toks if t in sw) / len(toks) for code, sw in self.langs}

    def detect(self, text: str, min_tokens: int = 3, min_score: float = 0.12, margin: float = 0.04) -> str | None:
        if len(TOKEN.findall(text)) < min_tokens:
            return None
        sc = sorted(self.scores(text).items(), key=lambda kv: -kv[1])
        if not sc or sc[0][1] < min_score:
            return None
        if len(sc) > 1 and sc[0][1] - sc[1][1] < margin:
            return None
        return sc[0][0]

    def distribution(self, text: str) -> dict[str, int]:
        """Paragraph counts per language (used for EDA)."""
        out: dict[str, int] = {}
        for p in re.split(r"\n\s*\n", text):
            if p.strip():
                k = self.detect(p) or "unknown"
                out[k] = out.get(k, 0) + 1
        return out


async def load_detector(force: bool = False) -> Detector:
    if not force and _cache["det"] and time.time() - _cache["t"] < 60:
        return _cache["det"]
    async with tx(bypass=True) as conn:
        rows = await q(conn, "SELECT code, name, stopwords FROM languages WHERE is_enabled ORDER BY position, code")
    _cache.update(t=time.time(), det=Detector(rows))
    return _cache["det"]


def invalidate_cache():
    _cache["t"] = 0.0
