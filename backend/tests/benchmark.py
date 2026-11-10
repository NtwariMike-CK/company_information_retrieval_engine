"""Performance benchmark for the RAG platform. Uses the built-in `fake` AI providers, so it measures the
WARNING: this script switches the GLOBAL RAG configuration to the test (fake) AI providers and creates test companies.
Run it only against a throwaway stack (docker compose down -v, up, run, then down -v again), never against your real data.
SYSTEM's own cost (HTTP, auth, retrieval, database, ingestion) and NOT Google's response time.

Needs a RUNNING API (default http://localhost:8000) and direct database access.
    BASE_URL=http://localhost:8000 DATABASE_URL=postgresql://rag_app:change_me_app@localhost:5432/company_rag \
    python tests/benchmark.py --part all            # or: --part api | --part retrieval
Results are merged into benchmark_results.json (run it on every machine you want to compare).
"""
import argparse, json, os, platform, random, statistics, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx

BASE = os.getenv("BASE_URL", "http://localhost:8000")
DB = os.getenv("DATABASE_URL", "postgresql://rag_app:change_me_app@localhost:5432/company_rag")
SA = (os.getenv("SUPERADMIN_EMAIL", "superadmin@example.com"), os.getenv("SUPERADMIN_PASSWORD", "ChangeMe123!"))
OUT = os.getenv("BENCH_OUT", "benchmark_results.json")
WORDS = ("policy leave employee manager approval expense travel report budget invoice contract safety training "
         "payroll holiday remote office laptop security password access vendor client project deadline review").split()


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 1)


def summary(ms):
    return {"n": len(ms), "mean_ms": round(statistics.mean(ms), 1), "p50_ms": pct(ms, 50), "p95_ms": pct(ms, 95), "max_ms": round(max(ms), 1)}


def environment():
    env = {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(), "cpu_count": os.cpu_count()}
    try:
        import psutil
        env["ram_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
        procs = [p for p in psutil.process_iter(["cmdline", "memory_info"]) if "uvicorn" in " ".join(p.info["cmdline"] or [])]
        if procs:
            env["api_rss_mb_start"] = round(sum(p.info["memory_info"].rss for p in procs) / 2**20, 1)
    except Exception:
        pass
    return env


def api_rss_mb():
    try:
        import psutil
        procs = [p for p in psutil.process_iter(["cmdline", "memory_info"]) if "uvicorn" in " ".join(p.info["cmdline"] or [])]
        return round(sum(p.info["memory_info"].rss for p in procs) / 2**20, 1) if procs else None
    except Exception:
        return None


class ResourceMonitor:
    """Samples CPU and memory every 0.5 s while a section runs (needs psutil)."""
    def __init__(self):
        self.samples, self.stop_flag, self.thread = [], False, None

    def _loop(self):
        import psutil
        psutil.cpu_percent(interval=None)
        while not self.stop_flag:
            procs = [p for p in psutil.process_iter(["cmdline", "memory_info"]) if "uvicorn" in " ".join(p.info["cmdline"] or [])]
            api_mb = sum(p.info["memory_info"].rss for p in procs) / 2**20 if procs else None
            self.samples.append((psutil.cpu_percent(interval=0.5), psutil.virtual_memory().used / 2**20, api_mb))

    def __enter__(self):
        try:
            import threading, psutil  # noqa: F401
            self.thread = threading.Thread(target=self._loop, daemon=True); self.thread.start()
        except ImportError:
            pass
        return self

    def __exit__(self, *a):
        self.stop_flag = True
        if self.thread:
            self.thread.join(timeout=3)

    def result(self):
        if not self.samples:
            return None
        cpu, ram, api = [x[0] for x in self.samples], [x[1] for x in self.samples], [x[2] for x in self.samples if x[2] is not None]
        return {"samples": len(cpu), "cpu_mean_pct": round(statistics.mean(cpu), 1), "cpu_peak_pct": round(max(cpu), 1), "system_ram_peak_mb": round(max(ram)),
                "api_rss_peak_mb": round(max(api), 1) if api else None}


def api_part():
    c = httpx.Client(base_url=BASE, timeout=120)
    tok = lambda r: {"Authorization": "Bearer " + r.json()["access_token"]}
    sa = tok(c.post("/auth/login", json={"email": SA[0], "password": SA[1]}))
    c.put("/superadmin/rag-config", headers=sa, json={"embedding_cfg": {"provider": "fake"}, "llm_cfg": {"provider": "fake"},
          "retrieval_cfg": {"min_score": 0.25, "final_k": 4}, "chunking_cfg": {"strategy": "parent_child", "parent_size": 600, "child_size": 200, "overlap": 20}})
    run = uuid.uuid4().hex[:6]
    c.post("/superadmin/companies", headers=sa, json={"company_name": f"Bench {run}", "admin_name": "Bench Admin", "phone": "12345678", "email": f"b-{run}@x.com", "password": "Password123"})
    ha = tok(c.post("/auth/login", json={"email": f"b-{run}@x.com", "password": "Password123"}))
    c.post("/company/employees", headers=ha, json={"full_name": "Bench User", "email": f"e-{run}@x.com", "password": "Password123"})
    res = {"api_rss_mb_idle": api_rss_mb()}

    # 1. login (Argon2 password hashing is deliberately slow)
    lat = []
    for _ in range(15):
        t = time.perf_counter(); c.post("/auth/login", json={"email": f"e-{run}@x.com", "password": "Password123"}); lat.append((time.perf_counter() - t) * 1000)
    res["login"] = summary(lat)
    he = tok(c.post("/auth/login", json={"email": f"e-{run}@x.com", "password": "Password123"}))

    # 2. ingestion throughput on a ~1 MB document
    rnd = random.Random(7)
    paras = []
    for i in range(1400):
        paras.append(f"## Section {i}\n\n" + " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(60, 110))) + f" reference-{i}.")
    big = "\n\n".join(paras).encode()
    seed = ("# Leave policy\n\nEmployees receive twenty five days of annual leave per year.\n\n# Remote work\n\nStaff may work remotely three days per week.\n").encode()
    t0 = time.perf_counter()
    with ResourceMonitor() as mon_ing:
        c.post("/company/documents", headers=ha, files=[("files", ("big.md", big, "text/markdown")), ("files", ("policy.md", seed, "text/markdown"))])
        while True:
            docs = c.get("/company/documents", headers=ha).json()
            if all(d["status"] in ("ready", "failed") for d in docs):
                break
            time.sleep(0.5)
    res["resources_ingestion"] = mon_ing.result()
    big_doc = next(d for d in docs if d["filename"] == "big.md")
    secs = time.perf_counter() - t0
    res["ingestion"] = {"file_mb": round(len(big) / 2**20, 2), "status": big_doc["status"], "chunks": big_doc["chunks"], "seconds": round(secs, 1),
                        "chunks_per_sec": round(big_doc["chunks"] / secs, 1) if secs else None, "stages": "extract>clean>chunk>embed>index (fake embedder)"}
    c.post("/company/service/start", headers=ha)

    # 3. chat latency, sequential (retrieval + generation(fake) + database writes)
    qs = ["How many days of annual leave do employees receive?", "What is the remote work policy?", "Which reference covers section 12?",
          "How are expense reports approved?", "What is the cafeteria menu on Friday?", "Who approves travel budgets?", "Is remote work allowed?", "Tell me about leave"]
    lat, errors, conv = [], 0, None
    for i in range(40):
        if i % 8 == 0:
            conv = c.post("/chat/conversations", headers=he).json()["id"]
        t = time.perf_counter()
        r = c.post(f"/chat/conversations/{conv}/messages", headers=he, json={"question": qs[i % len(qs)]})
        lat.append((time.perf_counter() - t) * 1000); errors += r.status_code != 200
    res["chat_sequential"] = {**summary(lat), "errors": errors}

    # 4. concurrency: 10 users x 3 questions at the same time
    def user(_):
        cl = httpx.Client(base_url=BASE, timeout=120)
        cv = cl.post("/chat/conversations", headers=he).json()["id"]
        out = []
        for q in qs[:3]:
            t = time.perf_counter(); r = cl.post(f"/chat/conversations/{cv}/messages", headers=he, json={"question": q}); out.append(((time.perf_counter() - t) * 1000, r.status_code))
        return out
    t0 = time.perf_counter()
    with ResourceMonitor() as mon_chat, ThreadPoolExecutor(10) as ex:
        results = [x for part in ex.map(user, range(10)) for x in part]
    res["resources_10_users"] = mon_chat.result()
    wall = time.perf_counter() - t0
    res["chat_concurrent_10_users"] = {**summary([ms for ms, _ in results]), "errors": sum(1 for _, s in results if s != 200),
                                       "requests": len(results), "wall_seconds": round(wall, 1), "throughput_rps": round(len(results) / wall, 1)}
    res["api_rss_mb_after_load"] = api_rss_mb()
    return res


def retrieval_part(scales):
    import numpy as np
    import psycopg
    out = {}
    rng = np.random.default_rng(42)
    vocab = [f"w{i}" for i in range(3000)] + WORDS
    with psycopg.connect(DB, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.bypass_rls','on',false)")
        cid = conn.execute("INSERT INTO companies (name) VALUES (%s) RETURNING id", (f"Bench synthetic {uuid.uuid4().hex[:6]}",)).fetchone()[0]
        did = conn.execute("INSERT INTO documents (company_id, filename, file_type, size_bytes, storage_path, status, embedding_model, content_hash) VALUES (%s,'synthetic.txt','txt',1,'-','ready','bench','bench') RETURNING id", (cid,)).fetchone()[0]
        total = 0
        try:
            for scale in scales:
                add = scale - total
                t0 = time.perf_counter()
                with conn.cursor() as cur, cur.copy("COPY chunks (company_id, document_id, chunk_index, content, embedding) FROM STDIN") as cp:
                    for start in range(0, add, 1000):
                        n = min(1000, add - start)
                        v = rng.standard_normal((n, 768)).astype("float32"); v /= np.linalg.norm(v, axis=1, keepdims=True)
                        for j in range(n):
                            text = " ".join(rng.choice(vocab, 25))
                            cp.write_row((cid, did, total + start + j, text, "[" + ",".join(f"{x:.5f}" for x in v[j]) + "]"))
                load_s = time.perf_counter() - t0
                total = scale
                conn.execute("ANALYZE chunks")
                qv = rng.standard_normal((30, 768)).astype("float32"); qv /= np.linalg.norm(qv, axis=1, keepdims=True)
                lits = ["[" + ",".join(f"{x:.5f}" for x in q) + "]" for q in qv]
                sql = ("SELECT c.id FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.company_id=%s AND c.embedding IS NOT NULL AND d.embedding_model='bench' "
                       "ORDER BY c.embedding <=> %s::vector LIMIT 10")
                hn, ex_, rec = [], [], []
                for lit in lits:
                    t = time.perf_counter(); a = [r[0] for r in conn.execute(sql, (cid, lit)).fetchall()]; hn.append((time.perf_counter() - t) * 1000)
                    with conn.transaction():
                        conn.execute("SET LOCAL enable_indexscan = off"); conn.execute("SET LOCAL enable_bitmapscan = off")
                        t = time.perf_counter(); b = [r[0] for r in conn.execute(sql, (cid, lit)).fetchall()]; ex_.append((time.perf_counter() - t) * 1000)
                    rec.append(len(set(a) & set(b)) / 10)
                sp = []
                for _ in range(30):
                    q = " | ".join(random.sample(WORDS, 3))
                    t = time.perf_counter()
                    conn.execute("SELECT id, ts_rank_cd(tsv, (to_tsquery('simple',%s) || to_tsquery('english',%s))) FROM chunks WHERE company_id=%s AND tsv @@ (to_tsquery('simple',%s) || to_tsquery('english',%s)) ORDER BY 2 DESC LIMIT 20", (q, q, cid, q, q)).fetchall()
                    sp.append((time.perf_counter() - t) * 1000)
                out[str(scale)] = {"chunks": scale, "load_seconds": round(load_s, 1), "dense_hnsw": summary(hn), "dense_exact_scan": summary(ex_),
                                   "hnsw_recall_at_10": round(statistics.mean(rec), 3), "sparse_gin": summary(sp)}
        finally:
            conn.execute("DELETE FROM companies WHERE id=%s", (cid,))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["all", "api", "retrieval"], default="all")
    ap.add_argument("--scales", type=int, nargs="+", default=[5000, 20000])
    a = ap.parse_args()
    results = json.load(open(OUT)) if os.path.exists(OUT) else {}
    results["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results["environment"] = environment()
    if a.part in ("all", "api"):
        results["api"] = api_part(); print(json.dumps(results["api"], indent=1))
    if a.part in ("all", "retrieval"):
        results["retrieval"] = retrieval_part(a.scales); print(json.dumps(results["retrieval"], indent=1))
    json.dump(results, open(OUT, "w"), indent=2)
    print("saved", OUT)
