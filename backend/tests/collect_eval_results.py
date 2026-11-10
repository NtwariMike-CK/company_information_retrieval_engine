"""Runs the starter benchmark through the Model Evaluation lab and saves the summaries as JSON evidence for the report.
WARNING: switches the GLOBAL RAG configuration to the test (fake) AI providers - use a throwaway stack.
For a REAL result, run the same runs from the SuperAdmin > Model evaluation page with your Gemini configuration.
    python tests/collect_eval_results.py  [output.json]"""
import json, os, sys, time
import httpx

BASE = os.getenv("BASE_URL", "http://localhost:8000")
SA = (os.getenv("SUPERADMIN_EMAIL", "superadmin@example.com"), os.getenv("SUPERADMIN_PASSWORD", "ChangeMe123!"))
OUT = sys.argv[1] if len(sys.argv) > 1 else "eval_results.json"
P = "/superadmin/model-eval"
c = httpx.Client(base_url=BASE, timeout=60)
sa = {"Authorization": "Bearer " + c.post("/auth/login", json={"email": SA[0], "password": SA[1]}).json()["access_token"]}
c.put("/superadmin/rag-config", headers=sa, json={"embedding_cfg": {"provider": "fake", "model": "gemini-embedding-2"}, "llm_cfg": {"provider": "fake"},
      "retrieval_cfg": {"min_score": 0.25, "final_k": 4}, "chunking_cfg": {"strategy": "parent_child", "parent_size": 600, "child_size": 200, "overlap": 20}})
sid = next(d["id"] for d in c.get(f"{P}/datasets", headers=sa).json() if d["is_starter"])


def run(kind, **params):
    rid = c.post(f"{P}/runs", headers=sa, json={"dataset_id": sid, "kind": kind, "params": params}).json()["id"]
    while True:
        r = c.get(f"{P}/runs/{rid}", headers=sa).json()
        if r["status"] in ("completed", "failed"):
            return r
        time.sleep(1)


out = {"note": "Produced with the built-in TEST AI providers (hashing embedder + scripted LLM). Shows the evaluation machinery works; "
               "it is NOT a measurement of Gemini quality.", "dataset": "starter benchmark (4 documents, 21 questions, EN+RW)"}
out["retrieval"] = run("retrieval")
out["llm_oracle"] = run("llm", mode="oracle", use_judge=True)
out["llm_pipeline"] = run("llm", mode="pipeline", use_judge=True)
out["llm_closed_book"] = run("llm", mode="closed_book", use_judge=False)
for k in ("retrieval", "llm_oracle", "llm_pipeline", "llm_closed_book"):
    print(k, out[k]["status"])
json.dump(out, open(OUT, "w"), indent=1, default=str)
print("saved", OUT)
