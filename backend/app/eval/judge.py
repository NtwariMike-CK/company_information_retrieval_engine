"""LLM-as-judge for faithfulness, relevance and abstention. Uses the configured LLM at temperature 0.
Limitation (documented): a model judging its own family of outputs can be biased, so the deterministic metrics
(key-fact recall, token F1, language match) are always reported next to the judged ones."""
import json
import re

JUDGE_SYSTEM = "You are an impartial evaluator of a question-answering system. Reply with ONLY one JSON object and no other text."


def parse_judge_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        total = max(0, int(d.get("claims_total", 0)))
        supported = max(0, min(total, int(d.get("claims_supported", 0))))
        relevance = max(0, min(5, int(d.get("relevance", 0))))
        return {"claims_total": total, "claims_supported": supported, "relevance": relevance, "abstained": bool(d.get("abstained", False))}
    except (ValueError, TypeError):
        return None


class LLMJudge:
    def __init__(self, llm):
        self.llm = llm

    async def judge(self, question: str, context: str, answer: str) -> dict | None:
        prompt = (f"Question:\n{question}\n\nContext given to the system:\n{context or '(no context was available)'}\n\n"
                  f"Answer to evaluate:\n{answer}\n\nReturn a JSON object with exactly these keys:\n"
                  '"claims_total": number of distinct factual claims in the answer (0 if it makes none),\n'
                  '"claims_supported": how many of those claims are directly supported by the context above,\n'
                  '"relevance": integer 0-5, how well the answer addresses the question (5 = fully),\n'
                  '"abstained": true if the answer says the information is not available or could not be found, otherwise false.')
        result = await self.llm.generate(JUDGE_SYSTEM, [], prompt)
        return parse_judge_json(result.text)
