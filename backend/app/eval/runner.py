"""Model-evaluation runner. Executed by the background worker.

CorpusPreparer      puts the benchmark documents through the REAL ingestion pipeline (clean -> chunk -> embed -> index)
                    inside a hidden system company, re-ingesting only when cleaning/chunking/embedding settings changed.
RetrievalEvaluator  embedding + retrieval metrics: dense-only (= embedding quality), keyword-only, hybrid (RRF);
                    language-pair breakdown, evidence integrity (chunking), parent-context recall, no-answer threshold analysis.
LLMEvaluator        answer metrics: key-fact recall, token F1, faithfulness, relevance, language match, abstention.
                    mode 'oracle' feeds the gold evidence (isolates the LLM), mode 'pipeline' uses real retrieval (end to end)."""
import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path

from psycopg.types.json import Jsonb

from ..db import ex, q, q1, tx
from ..rag.ai import AIError, RateLimitError, get_embedder, get_llm
from ..rag.lang import load_detector
from ..rag.retrieval import dense_search, load_context, retrieve, rrf_fuse, sparse_search
from ..services.chat import build_user_prompt, language_directive
from ..services.common import log_error
from ..services.config_service import get_active, resolve_key
from ..services.ingest import process_job
from . import metrics as M
from .judge import LLMJudge

log = logging.getLogger("eval")
MODES = ("dense", "sparse", "hybrid")


class EvalError(Exception):
    pass


def r4(x):
    return None if x is None else round(float(x), 4)


def ingest_fingerprint(cfg) -> str:
    """Settings that change the chunks. When they change, the benchmark documents are re-processed."""
    blob = json.dumps({"clean": cfg.cleaning_cfg.model_dump(mode="json"), "chunk": cfg.chunking_cfg.model_dump(mode="json"),
                       "emb": [cfg.embedding_cfg.provider, cfg.embedding_cfg.model, cfg.embedding_cfg.dimensions]}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def describe_config(cfg) -> dict:
    e, l = cfg.embedding_cfg, cfg.llm_cfg
    return {"config_version": cfg.version, "embedding": {"provider": e.provider, "model": e.model, "dimensions": e.dimensions},
            "chunking": cfg.chunking_cfg.model_dump(mode="json"), "cleaning": cfg.cleaning_cfg.model_dump(mode="json"),
            "retrieval": cfg.retrieval_cfg.model_dump(mode="json"), "llm": {"provider": l.provider, "model": l.model, "temperature": l.temperature}}


async def set_progress(run_id, pct, msg):
    async with tx(bypass=True) as conn:
        await ex(conn, "UPDATE eval_runs SET progress_pct=%s, message=%s WHERE id=%s", int(pct), msg[:300], run_id)


# ----------------------------------------------------------------------------- corpus
class CorpusPreparer:
    def __init__(self, dataset: dict, cfg, report):
        self.ds, self.cfg, self.report = dataset, cfg, report

    async def prepare(self) -> list[dict]:
        fp = ingest_fingerprint(self.cfg)
        async with tx(bypass=True) as conn:
            docs = await q(conn, "SELECT * FROM eval_documents WHERE dataset_id=%s ORDER BY filename", self.ds["id"])
        for n, ed in enumerate(docs):
            await self.report(2 + 18 * n / max(1, len(docs)), f"Preparing benchmark documents ({n + 1}/{len(docs)}): {ed['filename']}")
            if await self._is_current(ed, fp):
                continue
            job, doc_id = await self._start_job(ed)
            await process_job(job)                                   # the production pipeline, run inline
            async with tx(bypass=True) as conn:
                d = await q1(conn, "SELECT status FROM documents WHERE id=%s", doc_id)
                if not d or d["status"] != "ready":
                    raise EvalError(f"Benchmark document '{ed['filename']}' could not be processed (see error logs).")
                await ex(conn, "UPDATE eval_documents SET ingest_fingerprint=%s WHERE id=%s", fp, ed["id"])
        async with tx(bypass=True) as conn:
            return await q(conn, """SELECT c.id, c.content, c.parent_id, c.chunk_index, d.filename, ed.language AS doc_language
                                    FROM chunks c JOIN documents d ON d.id = c.document_id
                                    LEFT JOIN eval_documents ed ON ed.document_id = d.id
                                    WHERE c.company_id = %s ORDER BY d.filename, c.chunk_index""", self.ds["company_id"])

    async def _is_current(self, ed, fp) -> bool:
        if not ed["document_id"] or ed["ingest_fingerprint"] != fp:
            return False
        async with tx(bypass=True) as conn:
            d = await q1(conn, "SELECT status FROM documents WHERE id=%s", ed["document_id"])
        return bool(d and d["status"] == "ready")

    async def _start_job(self, ed):
        data = Path(ed["storage_path"]).read_bytes()
        digest = hashlib.sha256(data + str(self.ds["id"]).encode()).hexdigest()
        async with tx(bypass=True) as conn:
            doc_id = ed["document_id"]
            if not (doc_id and await q1(conn, "SELECT 1 FROM documents WHERE id=%s", doc_id)):
                row = await q1(conn, """INSERT INTO documents (company_id, filename, file_type, size_bytes, storage_path, content_hash, status)
                                        VALUES (%s,%s,%s,%s,%s,%s,'uploaded') RETURNING id""",
                               self.ds["company_id"], ed["filename"], ed["file_type"], len(data), ed["storage_path"], digest)
                doc_id = row["id"]
                await ex(conn, "UPDATE eval_documents SET document_id=%s WHERE id=%s", doc_id, ed["id"])
            else:
                await ex(conn, "UPDATE documents SET status='uploaded', error_message=NULL WHERE id=%s", doc_id)
            job = await q1(conn, """INSERT INTO processing_jobs (company_id, document_id, status, attempts, started_at, stage)
                                    VALUES (%s,%s,'running',1,now(),'extract') RETURNING *""", self.ds["company_id"], doc_id)
        return job, doc_id


def relevant_chunks(case: dict, corpus: list[dict]) -> list[dict]:
    """Chunks that contain the ground-truth evidence phrases (robust to any chunking configuration)."""
    ev = [e for e in (case["evidence"] or []) if e and e.strip()]
    if not case["answerable"] or not ev:
        return []
    return [c for c in corpus if any(M.phrase_in(e, c["content"]) for e in ev)]


def snippet(text: str, n: int = 220) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n] + "..."


# ----------------------------------------------------------------------------- retrieval / embedding
class RetrievalEvaluator:
    def __init__(self, run, ds, cases, cfg, corpus, stopwords, ekey, report):
        self.run_row, self.ds, self.cases, self.cfg, self.corpus = run, ds, cases, cfg, corpus
        self.stopwords, self.ekey, self.report = stopwords, ekey, report
        self.by_id = {c["id"]: c for c in corpus}

    async def run(self):
        cfg, rc = self.cfg, self.cfg.retrieval_cfg
        pause = float(self.run_row["params"].get("pause_seconds", 0) or 0)
        vecs, embed_ms = [None] * len(self.cases), None
        if rc.dense.enabled:
            embedder, bs, out, t0 = get_embedder(cfg.embedding_cfg, self.ekey), cfg.embedding_cfg.batch_size, [], time.perf_counter()
            for i in range(0, len(self.cases), bs):
                out += await embedder.embed([c["question"] for c in self.cases[i:i + bs]], "RETRIEVAL_QUERY")
                if pause and i + bs < len(self.cases):
                    await asyncio.sleep(pause)
            vecs, embed_ms = out, (time.perf_counter() - t0) * 1000 / len(self.cases)
        results, lat = [], {"dense": [], "sparse": []}
        async with tx(bypass=True) as conn:
            for i, case in enumerate(self.cases):
                await self.report(20 + 72 * i / len(self.cases), f"Evaluating question {i + 1}/{len(self.cases)}")
                results.append(await self._one(conn, case, vecs[i], lat))
        summary = self._summarise(results, lat, embed_ms)
        return summary, [(r["case"]["id"], r["case"]["question"], r["metrics"], r["details"]) for r in results]

    async def _one(self, conn, case, vec, lat):
        rc, cid, model = self.cfg.retrieval_cfg, self.ds["company_id"], self.cfg.embedding_cfg.model
        ev = [e for e in (case["evidence"] or []) if e and e.strip()]
        relevant = {c["id"] for c in relevant_chunks(case, self.corpus)}
        dense = sparse = []
        if rc.dense.enabled and vec is not None:
            t = time.perf_counter(); dense = await dense_search(conn, cid, vec, 10, model); lat["dense"].append((time.perf_counter() - t) * 1000)
        if rc.sparse.enabled:
            t = time.perf_counter(); sparse = await sparse_search(conn, cid, case["question"], 10, self.stopwords); lat["sparse"].append((time.perf_counter() - t) * 1000)
        fused = rrf_fuse(dense, sparse, rc.rrf_k)
        ranked = {"dense": [r["id"] for r in dense[:10]], "sparse": [r["id"] for r in sparse[:10]], "hybrid": [c["id"] for c in fused[:10]]}
        m = {"answerable": bool(case["answerable"]), "evidence_located": bool(relevant), "relevant_chunks": len(relevant)}
        if case["answerable"] and relevant:
            for mode, ids in ranked.items():
                m[mode] = M.rank_metrics([i in relevant for i in ids], len(relevant))
        top = [c["id"] for c in fused[:rc.final_k]]
        ctxs = await load_context(conn, top) if top else []
        if case["answerable"] and ev:
            m["context_recall_child"] = M.evidence_fraction(ev, " ".join(self.by_id[i]["content"] for i in top if i in self.by_id))
            m["context_recall_parent"] = M.evidence_fraction(ev, " ".join(c["text"] for c in ctxs))
        m["max_dense_score"] = float(dense[0]["score"]) if dense else None
        m["evidence_flag"] = (any(c["dense_score"] is not None and c["dense_score"] >= rc.min_score for c in fused[:rc.final_k]) if rc.dense.enabled else bool(fused))

        def rows(mode, items, key):
            out = []
            for rank, it in enumerate(items[:10], 1):
                ch = self.by_id.get(it["id"], {})
                out.append({"rank": rank, "chunk_id": str(it["id"]), "score": r4(it[key]), "relevant": it["id"] in relevant,
                            "source": ch.get("filename"), "text": snippet(ch.get("content", ""))})
            return out
        details = {"dense": rows("dense", dense, "score"), "sparse": rows("sparse", sparse, "score"), "hybrid": rows("hybrid", fused, "fused_score"),
                   "question_language": case["question_language"], "document_language": case["document_language"], "expected_answer": case["expected_answer"], "evidence": ev}
        return {"case": case, "metrics": m, "details": details}

    def _summarise(self, results, lat, embed_ms):
        rc = self.cfg.retrieval_cfg
        ans = [r for r in results if r["metrics"]["answerable"]]
        unans = [r for r in results if not r["metrics"]["answerable"]]
        elig = [r for r in ans if r["metrics"]["evidence_located"]]
        enabled = [m for m in MODES if (m == "hybrid" or (m == "dense" and rc.dense.enabled) or (m == "sparse" and rc.sparse.enabled))]
        modes = {}
        for mode in enabled:
            ms = [r["metrics"][mode] for r in elig]
            if not ms:
                continue
            agg = {k: r4(M.mean([x[k] for x in ms])) for k in ms[0]}
            agg["n"] = len(ms)
            for k in ("hit@1", "hit@5"):
                agg[f"{k}_ci95"] = [r4(v) for v in M.wilson_interval(sum(x[k] for x in ms), len(ms))]
            modes[mode] = agg
        pairs: dict[str, list] = {}
        for r in elig:
            c = r["case"]
            pairs.setdefault(f"{c['question_language']}->{c['document_language'] or c['question_language']}", []).append(r)
        by_pair = {}
        for key, rs in pairs.items():
            by_pair[key] = {"n": len(rs)}
            for mode in ("dense", "hybrid"):
                if mode in enabled:
                    by_pair[key][mode] = {k: r4(M.mean([x["metrics"][mode][k] for x in rs])) for k in ("hit@1", "hit@5", "mrr")}
        gap = None
        base_mode = "dense" if "dense" in enabled else "hybrid"
        same = [x["metrics"][base_mode]["hit@5"] for k, rs in pairs.items() for x in rs if k.split("->")[0] == k.split("->")[1]]
        cross = [x["metrics"][base_mode]["hit@5"] for k, rs in pairs.items() for x in rs if k.split("->")[0] != k.split("->")[1]]
        if same and cross:
            gap = {"mode": base_mode, "same_language_hit@5": r4(M.mean(same)), "cross_language_hit@5": r4(M.mean(cross)), "gap": r4(M.mean(same) - M.mean(cross))}
        no_answer = {"available": False, "reason": "Needs dense retrieval and at least one answerable and one unanswerable question."}
        pos = [r["metrics"]["max_dense_score"] for r in ans if r["metrics"]["max_dense_score"] is not None]
        neg = [r["metrics"]["max_dense_score"] for r in unans if r["metrics"]["max_dense_score"] is not None]
        if rc.dense.enabled and pos and neg:
            curve, tp = M.threshold_sweep(pos, neg), sum(r["metrics"]["evidence_flag"] for r in ans)
            fp = sum(r["metrics"]["evidence_flag"] for r in unans)
            best = M.best_threshold(curve)
            no_answer = {"available": True, "current_min_score": rc.min_score,
                         "current": {k: r4(v) if isinstance(v, float) else v for k, v in M.confusion_metrics(tp, fp, len(ans) - tp, len(unans) - fp).items()},
                         "suggested_min_score": best["threshold"], "at_suggested": {k: r4(v) if isinstance(v, float) else v for k, v in best.items() if k != "threshold"},
                         "curve": [{"threshold": c["threshold"], "precision": r4(c["precision"]), "recall": r4(c["recall"]), "f1": r4(c["f1"])} for c in curve],
                         "mean_score_answerable": r4(M.mean(pos)), "mean_score_unanswerable": r4(M.mean(neg))}
        lengths = [len(c["content"]) for c in self.corpus]
        ctx_c = [r["metrics"]["context_recall_child"] for r in ans if "context_recall_child" in r["metrics"]]
        ctx_p = [r["metrics"]["context_recall_parent"] for r in ans if "context_recall_parent" in r["metrics"]]
        n_ans = len(ans)
        return {"kind": "retrieval", "n_cases": len(results), "n_answerable": n_ans, "n_unanswerable": len(unans), "n_evaluated": len(elig), "modes": modes, "by_language_pair": by_pair,
                "cross_language_gap": gap, "no_answer": no_answer,
                "evidence_integrity": {"value": r4(len(elig) / n_ans) if n_ans else None, "ci95": [r4(v) for v in M.wilson_interval(len(elig), n_ans)],
                                       "missing": [r["case"]["question"] for r in ans if not r["metrics"]["evidence_located"]],
                                       "note": "Share of answerable questions whose evidence text survives intact inside at least one chunk (measures cleaning + chunking)."},
                "context_recall": {"child_only": r4(M.mean(ctx_c)), "with_parent": r4(M.mean(ctx_p))},
                "chunking_stats": {"chunks": len(self.corpus), "parents": len({c["parent_id"] for c in self.corpus if c["parent_id"]}),
                                   "avg_chars": r4(M.mean(lengths)), "median_chars": M.percentile(lengths, 50), "p95_chars": M.percentile(lengths, 95)},
                "latency": {"embed_ms_per_query": r4(embed_ms), "dense_ms_p50": r4(M.percentile(lat["dense"], 50)), "dense_ms_p95": r4(M.percentile(lat["dense"], 95)),
                            "sparse_ms_p50": r4(M.percentile(lat["sparse"], 50)), "sparse_ms_p95": r4(M.percentile(lat["sparse"], 95))}}


# ----------------------------------------------------------------------------- LLM
class LLMEvaluator:
    def __init__(self, run, ds, cases, cfg, corpus, detector, ekey, lkey, report):
        self.run_row, self.ds, self.cases, self.cfg, self.corpus = run, ds, cases, cfg, corpus
        self.detector, self.ekey, self.lkey, self.report = detector, ekey, lkey, report

    async def run(self):
        cfg, params = self.cfg, self.run_row["params"]
        self.mode = params.get("mode", "oracle")
        pause = float(params.get("pause_seconds", 0) or 0)
        self.llm = get_llm(cfg.llm_cfg, self.lkey)
        self.judge = LLMJudge(get_llm(cfg.llm_cfg.model_copy(update={"temperature": 0.0, "max_output_tokens": 800}), self.lkey)) if params.get("use_judge", True) else None
        self.embedder = get_embedder(cfg.embedding_cfg, self.ekey) if self.mode == "pipeline" and cfg.retrieval_cfg.dense.enabled else None
        results, rate_limited = [], 0
        for i, case in enumerate(self.cases):
            await self.report(20 + 72 * i / len(self.cases), f"Generating and scoring answer {i + 1}/{len(self.cases)}")
            try:
                results.append(await self._one(case))
                rate_limited = 0
            except RateLimitError as e:
                rate_limited += 1
                results.append({"case": case, "metrics": {"error": 1.0, "answerable": bool(case["answerable"])}, "details": {"error": str(e)[:300]}})
                if rate_limited >= 3:
                    raise EvalError("Stopped: the AI provider keeps rate-limiting. Retry later, or set a pause between calls.")
            except AIError as e:
                results.append({"case": case, "metrics": {"error": 1.0, "answerable": bool(case["answerable"])}, "details": {"error": str(e)[:300]}})
            if pause:
                await asyncio.sleep(pause)
        return self._summarise(results), [(r["case"]["id"], r["case"]["question"], r["metrics"], r["details"]) for r in results]

    async def _one(self, case):
        cfg, cid = self.cfg, self.ds["company_id"]
        question, ev = case["question"], [e for e in (case["evidence"] or []) if e and e.strip()]
        if self.mode == "closed_book":                        # baseline: a generic chatbot that does not see the documents
            contexts, has_ev = [], False
        elif self.mode == "oracle":
            ids = [c["id"] for c in relevant_chunks(case, self.corpus)][:3]
            async with tx(bypass=True) as conn:
                contexts = await load_context(conn, ids) if ids else []
            has_ev = bool(contexts)
        else:
            vec = (await self.embedder.embed([question], "RETRIEVAL_QUERY"))[0] if self.embedder else None
            async with tx(bypass=True) as conn:
                fused, has_ev = await retrieve(conn, cid, question, vec, cfg.retrieval_cfg, cfg.embedding_cfg.model, self.detector.stopwords)
                contexts = await load_context(conn, [c["id"] for c in fused]) if has_ev else []
        qlang = self.detector.detect(question) or case["question_language"]
        directive = language_directive(qlang, self.detector.names)
        if self.mode == "closed_book":
            system, user_text = "You are a helpful assistant. Answer the question as accurately as you can.", f"{question}\n\n{directive}"
        else:
            system = cfg.prompt_cfg.system_prompt if has_ev else cfg.prompt_cfg.no_evidence_prompt
            user_text = build_user_prompt(question, contexts, directive)
        t0 = time.perf_counter()
        res = await self.llm.generate(system, [], user_text)
        latency = (time.perf_counter() - t0) * 1000
        answer = res.text
        m = {"answerable": bool(case["answerable"]), "latency_ms": latency, "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens, "had_context": bool(contexts)}
        facts = [f for f in (case["key_facts"] or []) if f and f.strip()]
        if case["answerable"]:
            m["key_fact_recall"] = M.key_fact_recall(answer, facts)
        if case["expected_answer"]:
            m["token_f1"] = M.token_f1(answer, case["expected_answer"])
        det = self.detector.detect(answer)
        m["language_match"] = None if det is None else float(det == case["question_language"])
        judged = None
        if self.judge:
            try:
                judged = await self.judge.judge(question, "\n\n".join(c["text"] for c in contexts)[:6000], answer)
            except RateLimitError:
                raise
            except AIError:
                judged = None
        if judged:
            if contexts:
                m["faithfulness"] = judged["claims_supported"] / judged["claims_total"] if judged["claims_total"] else 1.0
            if case["answerable"]:
                m["relevance"] = judged["relevance"] / 5
            m["abstained"] = float(judged["abstained"])
        else:
            m["abstained"] = float(M.looks_like_abstention(answer))
        details = {"answer": answer, "expected_answer": case["expected_answer"], "question_language": case["question_language"], "language_detected": det,
                   "contexts": [{"source": c["filename"], "text": snippet(c["text"], 300)} for c in contexts], "judge": judged, "judge_used": bool(self.judge),
                   "key_facts": [{"fact": f, "found": any(M.phrase_in(a, answer, min_fuzzy_tokens=99) for a in f.split("|") if a.strip())} for f in facts]}
        return {"case": case, "metrics": m, "details": details}

    def _summarise(self, results):
        ok = [r for r in results if "error" not in r["metrics"]]
        ans = [r["metrics"] for r in ok if r["metrics"]["answerable"]]
        unans = [r["metrics"] for r in ok if not r["metrics"]["answerable"]]
        col = lambda rows, k: [x.get(k) for x in rows if x.get(k) is not None]
        lm = col([r["metrics"] for r in ok], "language_match")
        by_lang = {}
        for r in ok:
            by_lang.setdefault(r["case"]["question_language"], []).append(r["metrics"])
        return {"kind": "llm", "mode": self.mode, "judge": bool(self.judge), "n_cases": len(results), "n_scored": len(ok), "n_errors": len(results) - len(ok),
                "n_answerable": len(ans), "n_unanswerable": len(unans),
                "key_fact_recall": r4(M.mean(col(ans, "key_fact_recall"))), "fully_correct_rate": r4(M.mean([float(x["key_fact_recall"] == 1.0) for x in ans if x.get("key_fact_recall") is not None])),
                "token_f1": r4(M.mean(col(ans, "token_f1"))), "faithfulness": r4(M.mean(col(ans, "faithfulness"))), "relevance": r4(M.mean(col(ans, "relevance"))),
                "language_match": {"value": r4(M.mean(lm)), "n": len(lm), "ci95": [r4(v) for v in M.wilson_interval(sum(lm), len(lm))]},
                "abstention_accuracy": {"value": r4(M.mean(col(unans, "abstained"))), "n": len(unans), "ci95": [r4(v) for v in M.wilson_interval(sum(col(unans, "abstained")), len(unans))]},
                "false_abstention_rate": {"value": r4(M.mean(col(ans, "abstained"))), "n": len(ans)},
                "latency": {"mean_ms": r4(M.mean(col([r["metrics"] for r in ok], "latency_ms"))), "p50_ms": r4(M.percentile(col([r["metrics"] for r in ok], "latency_ms"), 50)),
                            "p95_ms": r4(M.percentile(col([r["metrics"] for r in ok], "latency_ms"), 95))},
                "tokens": {"prompt": sum(x.get("prompt_tokens") or 0 for x in [r["metrics"] for r in ok]), "completion": sum(x.get("completion_tokens") or 0 for x in [r["metrics"] for r in ok])},
                "by_language": {lang: {"n": len(rows), "key_fact_recall": r4(M.mean(col([x for x in rows if x["answerable"]], "key_fact_recall"))),
                                       "token_f1": r4(M.mean(col([x for x in rows if x["answerable"]], "token_f1"))), "language_match": r4(M.mean(col(rows, "language_match"))),
                                       "faithfulness": r4(M.mean(col(rows, "faithfulness")))} for lang, rows in by_lang.items()}}


# ----------------------------------------------------------------------------- entry point
async def process_eval_run(run: dict):
    run_id = run["id"]
    try:
        async with tx(bypass=True) as conn:
            ds = await q1(conn, "SELECT * FROM eval_datasets WHERE id=%s", run["dataset_id"])
            if not ds:
                raise EvalError("The dataset no longer exists.")
            cases = await q(conn, "SELECT * FROM eval_cases WHERE dataset_id=%s ORDER BY position, created_at", ds["id"])
            n_docs = (await q1(conn, "SELECT count(*) AS n FROM eval_documents WHERE dataset_id=%s", ds["id"]))["n"]
            cfg = await get_active(conn)
            ekey = await resolve_key(conn, cfg.embedding_cfg.credential_id) if cfg.embedding_cfg.provider == "google" else ""
            lkey = await resolve_key(conn, cfg.llm_cfg.credential_id) if cfg.llm_cfg.provider == "google" else ""
            await ex(conn, "UPDATE eval_runs SET config_snapshot=%s WHERE id=%s", Jsonb(describe_config(cfg)), run_id)
        if not cases or not n_docs:
            raise EvalError("The dataset needs at least one document and one question.")
        report = lambda pct, msg: set_progress(run_id, pct, msg)
        corpus = await CorpusPreparer(ds, cfg, report).prepare()
        if not corpus:
            raise EvalError("No chunks were produced from the benchmark documents.")
        detector = await load_detector()
        if run["kind"] == "retrieval":
            ev = RetrievalEvaluator(run, ds, cases, cfg, corpus, detector.stopwords, ekey, report)
        else:
            ev = LLMEvaluator(run, ds, cases, cfg, corpus, detector, ekey, lkey, report)
        summary, rows = await ev.run()
        async with tx(bypass=True) as conn:
            await ex(conn, "DELETE FROM eval_case_results WHERE run_id=%s", run_id)
            async with conn.cursor() as cur:
                await cur.executemany("INSERT INTO eval_case_results (run_id, case_id, question, metrics, details) VALUES (%s,%s,%s,%s,%s)",
                                      [(run_id, cid, qn, Jsonb(m), Jsonb(d)) for cid, qn, m, d in rows])
            await ex(conn, "UPDATE eval_runs SET status='completed', summary=%s, progress_pct=100, message='Completed', finished_at=now() WHERE id=%s", Jsonb(summary), run_id)
    except Exception as e:
        await log_error("evaluation", type(e).__name__, f"evaluation run {run_id} failed", repr(e))
        async with tx(bypass=True) as conn:
            await ex(conn, "UPDATE eval_runs SET status='failed', error=%s, message='Failed', finished_at=now() WHERE id=%s", str(e)[:500], run_id)
