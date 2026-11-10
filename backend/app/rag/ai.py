"""Embedding + LLM provider adapters. Swap providers via the SuperAdmin config ("google" or "fake")."""
import asyncio, hashlib, json, math, re
from dataclasses import dataclass

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"


class AIError(Exception):
    pass


class RateLimitError(AIError):
    pass


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


async def _post(url: str, key: str, body: dict, timeout: float = 90) -> dict:
    last = None
    for attempt in range(6):
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body)
        except httpx.HTTPError as e:
            last = AIError(f"network error: {e}")
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                last = RateLimitError(r.text[:300])
            elif r.status_code >= 500:
                last = AIError(f"provider error {r.status_code}: {r.text[:300]}")
            else:
                raise AIError(f"provider rejected request ({r.status_code}): {r.text[:300]}")
        if not isinstance(last, RateLimitError) and attempt >= 3:
            break                       # network / server errors: give up after ~7 seconds
        # rate limited: wait much longer (free tier allows only a burst per minute)
        await asyncio.sleep(15 * (attempt + 1) if isinstance(last, RateLimitError) else 2 ** attempt)
    raise last


# ------------------------------ embeddings ------------------------------
def v2_prefix(text: str, task: str) -> str:
    """gemini-embedding-2 has no task_type parameter: the task goes into the text (per Google's docs)."""
    if task == "RETRIEVAL_DOCUMENT":
        return f"title: none | text: {text}"
    if task == "RETRIEVAL_QUERY":
        return f"task: question answering | query: {text}"
    return f"task: sentence similarity | query: {text}"


class GoogleEmbedder:
    def __init__(self, model: str, dims: int, key: str):
        self.model, self.dims, self.key = model, dims, key
        self.v2 = model.startswith("gemini-embedding-2")

    async def embed(self, texts: list[str], task: str) -> list[list[float]]:
        if self.v2:
            reqs = [{"model": f"models/{self.model}", "content": {"parts": [{"text": v2_prefix(t, task)}]},
                     "outputDimensionality": self.dims} for t in texts]
        else:
            reqs = [{"model": f"models/{self.model}", "content": {"parts": [{"text": t}]},
                     "taskType": task, "outputDimensionality": self.dims} for t in texts]
        body = {"requests": reqs}
        data = await _post(f"{BASE}/models/{self.model}:batchEmbedContents", self.key, body)
        out = [e["values"] for e in data.get("embeddings", [])]
        if len(out) != len(texts):
            raise AIError("embedding response size mismatch")
        return [_normalize(v) for v in out]   # reduced dimensions must be re-normalized


# tiny Kinyarwanda->English lexicon so the offline fake model can exercise cross-language retrieval in tests
FAKE_LEXICON = {"abakozi": "employees", "bemerewe": "entitled", "iminsi": "days", "makumyabiri": "twenty", "itanu": "five",
                "ikiruhuko": "leave", "mwaka": "year", "ingahe": "many", "buri": "every"}


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder. For tests / local dev without an API key."""
    def __init__(self, dims: int):
        self.dims = dims

    async def embed(self, texts: list[str], task: str) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dims
            for w in re.findall(r"[^\W_]+", t.lower()):
                w = FAKE_LEXICON.get(w, w)
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                v[h % self.dims] += 1.0
            out.append(_normalize(v))
        return out


def get_embedder(cfg, api_key: str):
    if cfg.provider == "fake":
        return FakeEmbedder(cfg.dimensions)
    return GoogleEmbedder(cfg.model, cfg.dimensions, api_key)


# ------------------------------ LLM ------------------------------
class GoogleLLM:
    def __init__(self, cfg, key: str):
        self.cfg, self.key = cfg, key

    async def generate(self, system: str, history: list[dict], user_text: str) -> LLMResult:
        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in history]
        contents.append({"role": "user", "parts": [{"text": user_text}]})
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                "generationConfig": {"temperature": self.cfg.temperature, "maxOutputTokens": self.cfg.max_output_tokens}}
        data = await _post(f"{BASE}/models/{self.cfg.model}:generateContent", self.key, body, timeout=120)
        cands = data.get("candidates") or []
        if not cands:
            raise AIError(f"no candidates returned: {data.get('promptFeedback')}")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()   # never surface reasoning parts
        if not text:
            raise AIError(f"empty response (finishReason={cands[0].get('finishReason')})")
        u = data.get("usageMetadata") or {}
        return LLMResult(text, u.get("promptTokenCount"), u.get("candidatesTokenCount"))


class FakeLLM:
    async def generate(self, system: str, history: list[dict], user_text: str) -> LLMResult:
        if system.startswith("You are an impartial evaluator"):         # offline judge used by the tests
            ans = user_text.split("Answer to evaluate:\n", 1)[-1].split("\n\nReturn a JSON", 1)[0].lower()
            abst = any(p in ans for p in ("could not find", "sinabashije", "not find"))
            return LLMResult(json.dumps({"claims_total": 0 if abst else 2, "claims_supported": 0 if abst else 2, "relevance": 4, "abstained": abst}), 10, 10)
        rw = "Respond in Kinyarwanda" in user_text
        if "No relevant context was found" in user_text:
            return LLMResult("Sinabashije kubona ibisubizo muri dosiye z'ikigo. Mwongere mubaze mu bundi buryo." if rw
                             else "I could not find this in the company documents. Please rephrase or contact your administrator.", 10, 10)
        m = re.search(r"\[1\][^\n]*\n(.+?)(?:\n\n\[2\]|\n</context>)", user_text, re.S)
        return LLMResult(("Ukurikije dosiye z'ikigo: " if rw else "Based on the company documents: ") + (m.group(1)[:600] if m else ""), 10, 10)


def get_llm(cfg, api_key: str):
    return FakeLLM() if cfg.provider == "fake" else GoogleLLM(cfg, api_key)
