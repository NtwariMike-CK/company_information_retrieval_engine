"""Builds the evidence figures used by the testing / evaluation documents from the saved result files.
    python docs/report/build_figures.py        (run from the repository root)"""
import json, re
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
RES, FIG, LOGS = ROOT / "docs/testing/results", ROOT / "docs/figures", ROOT / "docs/testing/logs"
BLUE, SLATE, AMBER, GREY = "#1d4ed8", "#0f172a", "#d97706", "#94a3b8"
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#64748b", "figure.dpi": 150})
ev = json.loads((RES / "eval_results_test_providers.json").read_text())
bench = json.loads((RES / "benchmark_results_sandbox.json").read_text())


def labels(ax, bars, fmt="{:.2f}"):
    for b in bars:
        ax.annotate(fmt.format(b.get_height()), (b.get_x() + b.get_width() / 2, b.get_height()), ha="center", va="bottom", fontsize=7.5, xytext=(0, 2), textcoords="offset points")


# 1. retrieval ablation: dense vs keyword vs hybrid
S = ev["retrieval"]["summary"]["modes"]
metrics = [("hit@1", "Hit@1"), ("hit@5", "Hit@5"), ("hit@10", "Hit@10"), ("mrr", "MRR"), ("ndcg@10", "nDCG@10")]
fig, ax = plt.subplots(figsize=(7.2, 3.1))
w = 0.26
for i, (mode, col, name) in enumerate([("sparse", GREY, "Keyword only (baseline)"), ("dense", AMBER, "Embedding only"), ("hybrid", BLUE, "Hybrid (RRF) - the system")]):
    bars = ax.bar([x + (i - 1) * w for x in range(len(metrics))], [S[mode][k] for k, _ in metrics], w, label=name, color=col)
    labels(ax, bars)
ax.set_xticks(range(len(metrics)), [n for _, n in metrics]); ax.set_ylim(0, 1.12); ax.set_ylabel("score (0-1)")
ax.set_title("Retrieval quality on the starter benchmark (17 answerable questions, EN+RW)", fontsize=9.5, loc="left")
ax.legend(frameon=False, fontsize=7.5, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
fig.tight_layout(); fig.savefig(FIG / "eval_retrieval_modes.png"); plt.close(fig)

# 2. no-answer threshold sweep: precision / recall / F1 vs min_score
na = ev["retrieval"]["summary"]["no_answer"]; cur = na["curve"]
fig, ax = plt.subplots(figsize=(7.2, 2.9))
for key, col, name in (("precision", AMBER, "precision"), ("recall", GREY, "recall"), ("f1", BLUE, "F1")):
    ax.plot([p["threshold"] for p in cur], [p[key] for p in cur], color=col, lw=2 if key == "f1" else 1.4, label=name)
ax.axvline(na["current_min_score"], color=SLATE, ls="--", lw=1); ax.text(na["current_min_score"] + .01, .05, f"current min_score = {na['current_min_score']}", fontsize=7.5)
ax.set_xlabel("min_score (evidence threshold)"); ax.set_ylabel("answer-vs-abstain quality"); ax.set_ylim(0, 1.05)
ax.set_title("Evidence threshold sweep: when should the assistant answer?", fontsize=9.5, loc="left"); ax.legend(frameon=False, fontsize=8, ncol=3)
fig.tight_layout(); fig.savefig(FIG / "eval_no_answer_curve.png"); plt.close(fig)

# 3. LLM: RAG (gold context / real retrieval) vs closed-book baseline
runs = [("closed_book", "Baseline: LLM without\ndocuments", GREY), ("pipeline", "RAG: real retrieval", AMBER), ("oracle", "RAG: gold context\n(upper bound)", BLUE)]
fig, ax = plt.subplots(figsize=(7.2, 3.0))
for i, (m, name, col) in enumerate(runs):
    s = ev["llm_" + m]["summary"]
    bars = ax.bar([x + (i - 1) * 0.26 for x in range(2)], [s["key_fact_recall"], s["token_f1"]], 0.26, color=col, label=name.replace("\n", " "))
    labels(ax, bars)
ax.set_xticks(range(2), ["Key-fact recall", "Token F1"]); ax.set_ylim(0, 1.15)
ax.set_title("LLM answer quality: RAG vs no-documents baseline (test providers)", fontsize=9.5, loc="left"); ax.legend(frameon=False, fontsize=7.5, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
fig.tight_layout(); fig.savefig(FIG / "eval_llm_modes.png"); plt.close(fig)

# 4. performance: latency percentiles
api = bench["api"]
rows = [("Login", api["login"]), ("Chat, 1 user", api["chat_sequential"]), ("Chat, 10 users", api["chat_concurrent_10_users"])]
fig, ax = plt.subplots(figsize=(7.2, 2.8))
for i, (k, col) in enumerate((("p50_ms", BLUE), ("p95_ms", AMBER))):
    bars = ax.barh([j + (i - .5) * .36 for j in range(len(rows))], [r[1][k] for r in rows], .36, color=col, label=k.replace("_ms", "").upper())
    for b in bars:
        ax.annotate(f"{b.get_width():.0f} ms", (b.get_width(), b.get_y() + b.get_height() / 2), va="center", fontsize=7.5, xytext=(3, 0), textcoords="offset points")
ax.set_yticks(range(len(rows)), [r[0] for r in rows]); ax.invert_yaxis(); ax.set_xlabel("milliseconds (test AI providers, so Google's time is excluded)")
ax.set_title(f"API latency (2 vCPU sandbox) - throughput at 10 users: {api['chat_concurrent_10_users']['throughput_rps']} req/s", fontsize=9.5, loc="left")
ax.legend(frameon=False, fontsize=8); fig.tight_layout(); fig.savefig(FIG / "test_performance_latency.png"); plt.close(fig)

# 5. coverage per module from the integration coverage log
cov = []
for ln in (LOGS / "06_coverage_api_integration.log").read_text().splitlines():
    m = re.match(r"^(app/\S+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%", ln)
    if m and int(m.group(2)) > 0:
        cov.append((m.group(1).replace("app/", ""), int(m.group(4))))
cov.sort(key=lambda x: x[1])
fig, ax = plt.subplots(figsize=(7.2, 0.19 * len(cov) + 0.9))
bars = ax.barh([c[0] for c in cov], [c[1] for c in cov], color=[BLUE if c[1] >= 80 else AMBER for c in cov])
for b in bars:
    ax.annotate(f"{b.get_width():.0f}%", (b.get_width(), b.get_y() + b.get_height() / 2), va="center", fontsize=7, xytext=(3, 0), textcoords="offset points")
ax.set_xlim(0, 112); ax.set_xlabel("line coverage %"); ax.set_title("Statement coverage by module (all test suites running against the live API)", fontsize=9.5, loc="left"); ax.tick_params(axis="y", labelsize=7)
fig.tight_layout(); fig.savefig(FIG / "test_coverage_by_module.png"); plt.close(fig)
print("figures written:", sorted(p.name for p in FIG.glob("*.png")))

# 6. front-end load profiles (browser run)
e2e = json.loads((RES / "e2e_browser_results.json").read_text())
profiles = [(k, v) for k, v in e2e["perf"].items() if isinstance(v, dict)]
pages = list(profiles[0][1].keys())
short = {"Desktop, no throttling": "Desktop", "Mid-range phone (4x CPU slowdown, 4G 9 Mbps / 170 ms)": "Mid-range phone (4x CPU, 4G)", "Low-end phone (6x CPU slowdown, slow 3G 400 kbps / 400 ms)": "Low-end phone (6x CPU, slow 3G)"}
fig, ax = plt.subplots(figsize=(7.2, 3.1))
for i, ((name, rows), col) in enumerate(zip(profiles, (BLUE, AMBER, GREY))):
    bars = ax.bar([x + (i - 1) * 0.26 for x in range(len(pages))], [rows[p]["lcp_ms_median"] / 1000 for p in pages], 0.26, color=col, label=short.get(name, name))
    labels(ax, bars, "{:.1f}")
ax.set_xticks(range(len(pages)), [p.replace(" (", "\n(") for p in pages], fontsize=8); ax.set_ylabel("Largest Contentful Paint (seconds)")
ax.set_title("Front-end load by device profile (Chromium, median of 3 runs; 2.5 s = 'good' threshold)", fontsize=9, loc="left")
ax.axhline(2.5, color=SLATE, ls="--", lw=0.8); ax.legend(frameon=False, fontsize=7.5, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.2))
fig.tight_layout(); fig.savefig(FIG / "test_frontend_profiles.png"); plt.close(fig)


# 7. diagrams for the system documentation
from matplotlib.patches import FancyBboxPatch


def box(ax, x, y, w, h, text, fc="#eff6ff", ec=BLUE, fs=8, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=ec, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal", color=SLATE, linespacing=1.25)


def arrow(ax, x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=SLATE, lw=1.1))


fig, ax = plt.subplots(figsize=(7.4, 3.6)); ax.set_xlim(0, 10); ax.set_ylim(0, 5); ax.axis("off")
box(ax, 0.1, 3.6, 2.2, 1.0, "Browser\nNext.js 14 (Vercel)\nEmployee | Company Admin\nSuperAdmin", fs=7.5)
box(ax, 3.1, 3.6, 2.6, 1.0, "FastAPI backend (Render)\nauth, roles, REST API\nRAG services", fs=7.5, fc="#dbeafe")
box(ax, 6.6, 3.6, 3.2, 1.0, "Background worker (same process)\ningestion | deletion\nevaluation runs | e-mail", fs=7.5)
box(ax, 3.1, 1.6, 2.6, 1.1, "PostgreSQL 16 + pgvector\nrow-level security per company\nvectors (HNSW) + full text (GIN)", fs=7.5, fc="#dbeafe")
box(ax, 6.6, 1.6, 3.2, 1.1, "Google AI Studio (Gemini)\nembedding model\nLLM  (keys encrypted in the DB)", fs=7.5, fc="#fef3c7", ec=AMBER)
box(ax, 0.1, 1.6, 2.2, 1.1, "File storage\noriginal uploads\n(deleted with the company)", fs=7.5)
arrow(ax, 2.3, 4.1, 3.1, 4.1); arrow(ax, 5.7, 4.1, 6.6, 4.1); arrow(ax, 4.4, 3.6, 4.4, 2.7); arrow(ax, 8.2, 3.6, 8.2, 2.7); arrow(ax, 3.4, 3.6, 1.2, 2.7); arrow(ax, 5.2, 3.6, 7.2, 2.7)
ax.text(8.3, 3.15, "embeddings", fontsize=6.5, color=SLATE); ax.text(5.9, 3.0, "query embedding + LLM", fontsize=6.5, color=SLATE); ax.text(1.0, 3.15, "uploaded files", fontsize=6.5, color=SLATE); ax.text(4.5, 3.1, "SQL", fontsize=6.5, color=SLATE)
ax.text(5, 0.7, "Every table row carries company_id. Queries filter by it AND the database enforces it (FORCE ROW LEVEL SECURITY).", ha="center", fontsize=8, color=SLATE, style="italic")
ax.set_title("System architecture", fontsize=10, loc="left"); fig.tight_layout(); fig.savefig(FIG / "diagram_architecture.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.4, 3.9)); ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
ax.text(0.1, 5.7, "A. Document -> knowledge base (background worker)", fontsize=8.5, fontweight="bold", color=BLUE)
steps = ["Upload\ntype, size,\nduplicate check", "Extract\nPDF / DOCX /\nTXT / MD", "Clean + EDA\nunicode, headers,\nhyphens, dupes", "Chunk\nparent-child,\nlanguage-aware", "Embed\ngemini-\nembedding-2", "Index\npgvector HNSW\n+ GIN full text"]
for i, t in enumerate(steps):
    box(ax, 0.1 + i * 1.65, 4.2, 1.45, 1.2, t, fs=7)
    if i:
        arrow(ax, 0.1 + i * 1.65 - 0.2, 4.8, 0.1 + i * 1.65, 4.8)
ax.text(0.1, 3.5, "B. Question -> answer (per request)", fontsize=8.5, fontweight="bold", color=BLUE)
qs = ["Validate\nrole, service on,\n9-question limit", "Detect language\n+ rewrite short\nfollow-ups", "Embed query\n(question mode)", "Retrieve\ndense top 20 +\nkeyword top 20", "Fuse (RRF)\nkeep top 6\nevidence check", "Expand parents\nbuild prompt\nwith sources", "Gemini LLM\ngrounded answer\nin user's language"]
for i, t in enumerate(qs):
    box(ax, 0.05 + i * 1.42, 1.9, 1.28, 1.25, t, fs=6.3, fc="#dbeafe" if i in (3, 4) else "#eff6ff")
    if i:
        arrow(ax, 0.05 + i * 1.42 - 0.14, 2.5, 0.05 + i * 1.42, 2.5)
box(ax, 0.05, 0.25, 9.3, 0.95, "Record: question, answer, retrieved chunks with dense / keyword / fused scores, tokens, latency  ->  optional rating + report  ->  analytics.\nNo evidence found? A different prompt makes the assistant say so politely instead of guessing.", fs=7.2, fc="#f1f5f9", ec=GREY)
arrow(ax, 9.0, 1.9, 9.0, 1.2)
fig.tight_layout(); fig.savefig(FIG / "diagram_pipeline.png"); plt.close(fig)
