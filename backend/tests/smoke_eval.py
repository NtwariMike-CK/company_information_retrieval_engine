"""End-to-end test of the model-evaluation lab against a RUNNING API (test AI providers, no Gemini key needed).
WARNING: switches the GLOBAL RAG configuration to the test (fake) AI providers. Use a throwaway stack.   python tests/smoke_eval.py"""
import os, sys, time, uuid
import httpx

BASE = os.getenv("BASE_URL", "http://localhost:8000")
SA = (os.getenv("SUPERADMIN_EMAIL", "superadmin@example.com"), os.getenv("SUPERADMIN_PASSWORD", "ChangeMe123!"))
c = httpx.Client(base_url=BASE, timeout=60)
ok = fail = 0
run = uuid.uuid4().hex[:6]
P = "/superadmin/model-eval"


def check(name, cond, extra=""):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {extra}" if not cond else ""))


def wait_run(rid, timeout=240):
    t = time.time()
    while time.time() - t < timeout:
        r = c.get(f"{P}/runs/{rid}", headers=sa).json()
        if r["status"] in ("completed", "failed"):
            return r
        time.sleep(1)
    return r


def between(x, lo=0.0, hi=1.0):
    return x is not None and lo <= x <= hi


sa = {"Authorization": "Bearer " + c.post("/auth/login", json={"email": SA[0], "password": SA[1]}).json()["access_token"]}
cfg = {"embedding_cfg": {"provider": "fake", "model": "gemini-embedding-2"}, "llm_cfg": {"provider": "fake"}, "retrieval_cfg": {"min_score": 0.25, "final_k": 4},
       "chunking_cfg": {"strategy": "parent_child", "parent_size": 600, "child_size": 200, "overlap": 20}}
c.put("/superadmin/rag-config", headers=sa, json=cfg)

# ---------- datasets: starter, CRUD, validation, access control ----------
ds = c.get(f"{P}/datasets", headers=sa).json()
starter = next((d for d in ds if d["is_starter"]), None)
check("starter benchmark seeded (4 documents, 21 questions, 17 answerable)", starter and starter["documents"] == 4 and starter["cases"] == 21 and starter["answerable_cases"] == 17, str(starter))
check("hidden evaluation workspaces are not listed as companies", not any("[System]" in x["name"] for x in c.get("/superadmin/companies", headers=sa).json()))
check("model-eval API is SuperAdmin-only", c.get(f"{P}/datasets", headers={"Authorization": "Bearer " + c.post("/public/register", json={"full_name": "Eve Test", "phone": "12345678", "email": f"ev-{run}@x.com", "password": "Password123"}).json()["access_token"]}).status_code == 403)
new = c.post(f"{P}/datasets", headers=sa, json={"name": f"Test set {run}", "description": "temporary"})
check("dataset created", new.status_code == 201, new.text[:200])
nid = new.json()["id"]
check("run on an empty dataset refused", c.post(f"{P}/runs", headers=sa, json={"dataset_id": nid, "kind": "retrieval"}).status_code == 409)
up = c.post(f"{P}/datasets/{nid}/documents", headers=sa, files=[("files", ("note.md", b"# Note\n\nThe cafeteria opens at eight in the morning every day.\n", "text/markdown")), ("files", ("bad.exe", b"MZ", "application/x-msdownload"))], data={"language": "en"})
res = up.json()["results"]
check("document added, .exe rejected", res[0]["status"] == "added" and res[1]["status"] == "rejected", up.text[:200])
check("answerable question without evidence is rejected", c.post(f"{P}/datasets/{nid}/cases", headers=sa, json={"question": "When does it open?", "answerable": True}).status_code == 422)
ok_case = c.post(f"{P}/datasets/{nid}/cases", headers=sa, json={"question": "When does the cafeteria open?", "evidence": ["The cafeteria opens at eight in the morning"], "key_facts": ["eight|8"]})
check("question with ground truth added", ok_case.status_code == 201)
imp = c.post(f"{P}/datasets/{nid}/cases/import", headers=sa, json=[{"question": "What is the meaning of life?", "answerable": False}, {"question": "Does the cafeteria open daily?", "evidence": ["opens at eight in the morning every day"]}])
check("bulk import", imp.status_code == 200 and imp.json()["imported"] == 2, imp.text[:200])
check("export is valid JSON with 3 questions", len(c.get(f"{P}/datasets/{nid}/cases/export", headers=sa).json()) == 3)
r_small = c.post(f"{P}/runs", headers=sa, json={"dataset_id": nid, "kind": "retrieval"}).json()
done = wait_run(r_small["id"])
check("retrieval run on a tiny custom dataset completes", done["status"] == "completed" and done["summary"]["n_cases"] == 3, str(done)[:300])
check("delete the temporary dataset", c.delete(f"{P}/datasets/{nid}", headers=sa).status_code == 200 and not any(d["id"] == nid for d in c.get(f"{P}/datasets", headers=sa).json()))

# ---------- retrieval / embedding evaluation on the starter benchmark ----------
sid = starter["id"]
r1 = c.post(f"{P}/runs", headers=sa, json={"dataset_id": sid, "kind": "retrieval"})
check("retrieval run accepted", r1.status_code == 202, r1.text[:200])
check("a second run on the same dataset is refused while one is active", c.post(f"{P}/runs", headers=sa, json={"dataset_id": sid, "kind": "retrieval"}).status_code == 409)
R = wait_run(r1.json()["id"])
S = R.get("summary") or {}
check("retrieval run completed", R["status"] == "completed", str(R.get("error")))
check("counts: 21 questions, 17 answerable, 4 unanswerable", (S.get("n_cases"), S.get("n_answerable"), S.get("n_unanswerable")) == (21, 17, 4), str((S.get("n_cases"), S.get("n_answerable"))))
check("three retrieval modes reported: dense (embedding), sparse (keyword), hybrid", set(S.get("modes", {})) == {"dense", "sparse", "hybrid"})
check("every metric is a valid probability", all(between(v) for m in S["modes"].values() for k, v in m.items() if isinstance(v, float)))
h = S["modes"]["hybrid"]
check("metric relations hold (hit@1 <= hit@3 <= hit@5 <= hit@10, MRR >= hit@1)", h["hit@1"] <= h["hit@3"] <= h["hit@5"] <= h["hit@10"] and h["mrr"] >= h["hit@1"])
check("keyword baseline finds same-language evidence (real, no AI model involved)", S["modes"]["sparse"]["hit@5"] >= 0.5, str(S["modes"]["sparse"]))
check("evidence integrity: chunking keeps the answer text intact", S["evidence_integrity"]["value"] >= 0.9, str(S["evidence_integrity"]))
check("language pairs reported (en->en, rw->rw, en->rw, rw->en)", {"en->en", "rw->rw", "en->rw", "rw->en"} <= set(S["by_language_pair"]), str(set(S["by_language_pair"])))
check("parent expansion never lowers context recall", S["context_recall"]["with_parent"] >= S["context_recall"]["child_only"] - 1e-9, str(S["context_recall"]))
na = S["no_answer"]
check("no-answer analysis: curve + suggested threshold", na["available"] and len(na["curve"]) == 51 and between(na["suggested_min_score"]), str(na)[:200])
check("latency and chunk statistics reported", S["latency"]["dense_ms_p50"] is not None and S["chunking_stats"]["chunks"] > 0)
check("run records the exact settings evaluated", R["config_snapshot"]["embedding"]["model"] == "gemini-embedding-2" and R["config_snapshot"]["chunking"]["strategy"] == "parent_child")
cases = c.get(f"{P}/runs/{R['id']}/cases", headers=sa).json()
check("per-question results with retrieved lists", len(cases) == 21 and len(cases[0]["details"]["hybrid"]) > 0 and "relevant" in cases[0]["details"]["hybrid"][0])
csv = c.get(f"{P}/runs/{R['id']}/export", headers=sa)
check("CSV export", csv.status_code == 200 and csv.text.startswith("question,"))

# ---------- re-ingestion when the chunking settings change ----------
chunks_before = S["chunking_stats"]["chunks"]
c.put("/superadmin/rag-config", headers=sa, json={"chunking_cfg": {"strategy": "parent_child", "parent_size": 400, "child_size": 120, "overlap": 10}})
R2 = wait_run(c.post(f"{P}/runs", headers=sa, json={"dataset_id": sid, "kind": "retrieval"}).json()["id"])
check("changing the chunking settings re-processes the benchmark (more, smaller chunks)", R2["status"] == "completed" and R2["summary"]["chunking_stats"]["chunks"] > chunks_before, f"{chunks_before} -> {R2.get('summary', {}).get('chunking_stats')}")
c.put("/superadmin/rag-config", headers=sa, json=cfg)

# ---------- LLM evaluation ----------
L = wait_run(c.post(f"{P}/runs", headers=sa, json={"dataset_id": sid, "kind": "llm", "params": {"mode": "oracle", "use_judge": True}}).json()["id"])
LS = L.get("summary") or {}
check("LLM run (gold context + judge) completed", L["status"] == "completed", str(L.get("error")))
check("key-fact recall high when the gold evidence is given", LS["key_fact_recall"] >= 0.6, str(LS.get("key_fact_recall")))
check("faithfulness and relevance reported (judge)", between(LS["faithfulness"]) and between(LS["relevance"]) and LS["judge"] is True)
check("abstention accuracy on unanswerable questions = 100%", LS["abstention_accuracy"]["value"] == 1.0 and LS["abstention_accuracy"]["n"] == 4, str(LS["abstention_accuracy"]))
check("language, token-F1, latency and token usage reported", LS["language_match"]["n"] > 0 and between(LS["token_f1"]) and LS["latency"]["p50_ms"] is not None and LS["tokens"]["prompt"] > 0)
check("breakdown by language", {"en", "rw"} <= set(LS["by_language"]))
Lc = wait_run(c.post(f"{P}/runs", headers=sa, json={"dataset_id": sid, "kind": "llm", "params": {"mode": "closed_book", "use_judge": False}}).json()["id"])
check("baseline (LLM without the documents) scores lower than RAG", Lc["status"] == "completed" and Lc["summary"]["key_fact_recall"] < LS["key_fact_recall"], f"{Lc.get('summary', {}).get('key_fact_recall')} vs {LS['key_fact_recall']}")
Lp = wait_run(c.post(f"{P}/runs", headers=sa, json={"dataset_id": sid, "kind": "llm", "params": {"mode": "pipeline", "use_judge": False}}).json()["id"])
check("end-to-end pipeline mode completes without judge", Lp["status"] == "completed" and Lp["summary"]["judge"] is False and Lp["summary"]["key_fact_recall"] is not None)
lc = c.get(f"{P}/runs/{L['id']}/cases", headers=sa).json()
check("per-question LLM results include answer, contexts and judge output", lc[0]["details"]["answer"] and "judge" in lc[0]["details"] and "key_facts" in lc[0]["details"])
check("runs list shows headline numbers", any(x["id"] == R["id"] and x["hybrid_hit5"] is not None for x in c.get(f"{P}/runs", headers=sa).json()))
check("finished runs can be deleted", c.delete(f"{P}/runs/{Lp['id']}", headers=sa).status_code == 200)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
