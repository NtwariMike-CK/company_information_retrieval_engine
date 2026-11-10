"""Builds the submission documents from report_content.py + report_inputs.json + benchmark results.

    pip install reportlab matplotlib
    python docs/report/build_report.py

Outputs (in docs/):  Technical_Report.pdf (max 5 pages), Scope_Alignment_and_Feature_Validation.pdf, SCOPE_ALIGNMENT.md
Anything still written as "[...]" in report_inputs.json is highlighted yellow so it cannot be missed."""
import json, os, sys
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DOCS = ROOT / "docs"
sys.path.insert(0, str(HERE))
import report_content as C  # noqa: E402

BLUE, DARK, GREY = colors.HexColor("#1d4ed8"), colors.HexColor("#0b1220"), colors.HexColor("#475569")
STATUS_COLOR = {C.COMPLETED: "#047857", C.PARTIAL: "#b45309", C.MISSING: "#b91c1c"}
PH_BG = "#fde68a"
PREFIX = {"B:": "backend/app/", "F:": "frontend/src/app/", "T:": "backend/tests/"}


# ----------------------------------------------------------------------------- data
def load_inputs():
    inp = json.loads((HERE / "report_inputs.json").read_text())
    bench = {}
    for key, name in (("sandbox", "benchmark_results_sandbox.json"), ("mac", "benchmark_results_macbook.json")):
        f = DOCS / name
        if key == "mac" and inp.get("macbook_benchmark_file"):
            f = ROOT / inp["macbook_benchmark_file"]
        bench[key] = json.loads(f.read_text()) if f.exists() else None
    return inp, bench


def resolved_scope(inp):
    rows = []
    for g, feat, purpose, status, evidence in C.SCOPE:
        if status == "@deployment":
            status, evidence = inp["deployment"]["status"], inp["deployment"]["evidence"]
        rows.append((g, feat, purpose, status, evidence))
    return rows


def is_ph(v):
    return not v or str(v).strip().startswith("[")


def expand(text):
    for k, v in PREFIX.items():
        text = text.replace(k, v)
    return text


def loc(paths, exts):
    n = 0
    for p in paths:
        for f in (ROOT / p).rglob("*"):
            if f.is_file() and f.suffix in exts and "node_modules" not in f.parts and "__pycache__" not in f.parts and ".next" not in f.parts:
                n += len(f.read_text(errors="ignore").splitlines())
    return n


# ----------------------------------------------------------------------------- styles / helpers
def styles(base=8.0):
    s = {}
    s["body"] = ParagraphStyle("body", fontName="Helvetica", fontSize=base, leading=base * 1.25, textColor=DARK, alignment=TA_LEFT, spaceAfter=2)
    s["h1"] = ParagraphStyle("h1", parent=s["body"], fontName="Helvetica-Bold", fontSize=base + 2.6, leading=base + 4, textColor=BLUE, spaceBefore=5, spaceAfter=2)
    s["h2"] = ParagraphStyle("h2", parent=s["body"], fontName="Helvetica-Bold", fontSize=base + 0.4, leading=base + 2, spaceBefore=3, spaceAfter=1, textColor=DARK)
    s["title"] = ParagraphStyle("title", parent=s["body"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=BLUE, spaceAfter=3)
    s["small"] = ParagraphStyle("small", parent=s["body"], fontSize=base - 1.3, leading=(base - 1.3) * 1.22, spaceAfter=0)
    s["cell"] = ParagraphStyle("cell", parent=s["body"], fontSize=base - 1.4, leading=(base - 1.4) * 1.2, spaceAfter=0)
    s["cellb"] = ParagraphStyle("cellb", parent=s["cell"], fontName="Helvetica-Bold", textColor=colors.white)
    s["cap"] = ParagraphStyle("cap", parent=s["body"], fontSize=base - 1.3, leading=(base - 1.3) * 1.2, textColor=GREY, spaceAfter=3)
    return s


def P(text, st):
    return Paragraph(text, st)


def ph(text):
    """Escape text; if it is a placeholder, highlight it."""
    t = escape(str(text))
    return f'<span backColor="{PH_BG}">{t}</span>' if is_ph(text) else t


def status_html(status):
    return f'<font color="{STATUS_COLOR.get(status, "#000000")}"><b>{escape(status)}</b></font>'


def grid(data, widths, header=True, zebra=True, pad=2.2):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
          ("LEFTPADDING", (0, 0), (-1, -1), pad + 0.5), ("RIGHTPADDING", (0, 0), (-1, -1), pad + 0.5),
          ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), BLUE)]
    if zebra:
        st += [("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")])]
    t.setStyle(TableStyle(st))
    return t


class NumberedCanvas(canvas.Canvas):
    footer = "Company RAG Chatbot - Technical Report"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Helvetica", 6.8)
            self.setFillColor(GREY)
            self.drawString(1.4 * cm, 0.75 * cm, self.footer)
            self.drawRightString(A4[0] - 1.4 * cm, 0.75 * cm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def scope_summary(rows):
    n = {C.COMPLETED: 0, C.PARTIAL: 0, C.MISSING: 0}
    for r in rows:
        n[r[3]] = n.get(r[3], 0) + 1
    return n


# ----------------------------------------------------------------------------- figures
def architecture_drawing(width=18.0 * cm):
    w, h = width, 112
    d = Drawing(w, h)
    k = w / 510.0

    def box(x, y, bw, bh, title, sub, fill):
        d.add(Rect(x * k, y, bw * k, bh, rx=4, ry=4, fillColor=fill, strokeColor=BLUE, strokeWidth=0.8))
        d.add(String((x + bw / 2) * k, y + bh - 14, title, fontName="Helvetica-Bold", fontSize=7.6, textAnchor="middle", fillColor=DARK))
        for i, line in enumerate(sub):
            d.add(String((x + bw / 2) * k, y + bh - 25 - i * 8.2, line, fontName="Helvetica", fontSize=6.3, textAnchor="middle", fillColor=GREY))

    def arrow(x1, y1, x2, y2, label=None, lx=0, ly=3):
        d.add(Line(x1 * k, y1, x2 * k, y2, strokeColor=BLUE, strokeWidth=1))
        import math
        a = math.atan2(y2 - y1, (x2 - x1) * k)
        for (px, py, ang) in ((x2 * k, y2, a), (x1 * k, y1, a + math.pi)):
            if (px, py) == (x1 * k, y1) and not label:
                continue
            p = [(px, py), (px - 5 * math.cos(ang - 0.4), py - 5 * math.sin(ang - 0.4)), (px - 5 * math.cos(ang + 0.4), py - 5 * math.sin(ang + 0.4))]
            d.add(Polygon([c for pt in p for c in pt], fillColor=BLUE, strokeColor=BLUE))
        if label:
            d.add(String(((x1 + x2) / 2 + lx) * k, (y1 + y2) / 2 + ly, label, fontName="Helvetica-Oblique", fontSize=5.8, textAnchor="middle", fillColor=GREY))

    lightblue, lightgrey = colors.HexColor("#dbeafe"), colors.HexColor("#f1f5f9")
    box(4, 56, 118, 50, "Browser: Next.js 14 (Vercel)", ["Landing, request & onboarding,", "admin dashboards, chat"], lightblue)
    box(170, 56, 172, 50, "FastAPI backend (Render)", ["routers -> services -> rag pipeline", "JWT auth, RBAC, validation (Pydantic)"], lightblue)
    box(390, 56, 116, 50, "PostgreSQL 16 + pgvector", ["33 tables, RLS, HNSW + GIN", "queue, audit, content (CMS)"], lightblue)
    box(170, 2, 84, 40, "Background worker", ["ingest, delete, email", "(SKIP LOCKED queue)"], lightgrey)
    box(268, 2, 74, 40, "Google Gemini API", ["embeddings + LLM"], lightgrey)
    box(390, 2, 116, 40, "File storage", ["uploaded documents (disk)"], lightgrey)
    arrow(122, 81, 170, 81, "REST + JWT", 0, 4)
    arrow(342, 81, 390, 81, "SQL + RLS", 0, 4)
    arrow(212, 56, 212, 42)
    arrow(305, 56, 305, 42, "AI calls", 14, -2)
    return d


def performance_chart(bench, out):
    a, r = bench["api"], bench["retrieval"]
    fig, ax = plt.subplots(1, 2, figsize=(7.1, 1.85), dpi=220)
    names = ["Login\n(Argon2)", "Chat\nsequential", "Chat\n10 users"]
    p50 = [a["login"]["p50_ms"], a["chat_sequential"]["p50_ms"], a["chat_concurrent_10_users"]["p50_ms"]]
    p95 = [a["login"]["p95_ms"], a["chat_sequential"]["p95_ms"], a["chat_concurrent_10_users"]["p95_ms"]]
    x = range(3)
    ax[0].bar([i - 0.2 for i in x], p50, 0.4, label="p50", color="#2563eb")
    ax[0].bar([i + 0.2 for i in x], p95, 0.4, label="p95", color="#93c5fd")
    ax[0].set_xticks(list(x)); ax[0].set_xticklabels(names, fontsize=6); ax[0].set_ylabel("ms", fontsize=6.5)
    ax[0].set_title("API latency (2 vCPU, test AI models)", fontsize=7)
    for i, v in enumerate(p50):
        ax[0].text(i - 0.2, v, f"{v:.0f}", ha="center", va="bottom", fontsize=5.5)
    scales = sorted(r, key=int)
    xs = range(len(scales)); wdt = 0.26
    for j, (key, lab, col) in enumerate((("dense_hnsw", "dense HNSW", "#1d4ed8"), ("dense_exact_scan", "dense exact scan", "#60a5fa"), ("sparse_gin", "keyword (GIN)", "#94a3b8"))):
        vals = [r[s][key]["p50_ms"] for s in scales]
        ax[1].bar([i + (j - 1) * wdt for i in xs], vals, wdt, label=lab, color=col)
        for i, v in zip(xs, vals):
            ax[1].text(i + (j - 1) * wdt, v, f"{v:.1f}", ha="center", va="bottom", fontsize=5.5)
    ax[1].set_xticks(list(xs)); ax[1].set_xticklabels([f"{int(s):,} chunks" for s in scales], fontsize=6.5)
    ax[1].set_title("Retrieval query time p50 (ms)", fontsize=7)
    for a_ in ax:
        a_.tick_params(labelsize=6); a_.spines[["top", "right"]].set_visible(False); a_.legend(fontsize=5.8, frameon=False)
    fig.tight_layout(pad=0.4)
    fig.savefig(out, dpi=220)
    plt.close(fig)


# ----------------------------------------------------------------------------- tables
def scope_table(rows, S, widths, expand_paths=False):
    data = [[P("Planned feature", S["cellb"]), P("Intended purpose", S["cellb"]), P("Status", S["cellb"]), P("Evidence (repository reference)", S["cellb"])]]
    for _, feat, purpose, status, ev in rows:
        data.append([P(escape(feat), S["cell"]), P(escape(purpose), S["cell"]), P(status_html(status), S["cell"]),
                     P(escape(expand(ev) if expand_paths else ev), S["cell"])])
    return grid(data, widths)


def changes_table(S, widths):
    data = [[P("Change", S["cellb"]), P("What changed", S["cellb"]), P("Justification", S["cellb"])]]
    for a, b, c in C.SCOPE_CHANGES:
        data.append([P(f"<b>{escape(a)}</b>", S["cell"]), P(escape(b), S["cell"]), P(escape(c), S["cell"])])
    return grid(data, widths)


def perf_table(bench, S, widths):
    sb, mac = bench["sandbox"], bench["mac"]

    def col(b, fn, fallback="[run benchmark.py on the MacBook]"):
        if b is None:
            return P(f'<span backColor="{PH_BG}">{escape(fallback)}</span>', S["cell"])
        try:
            return P(escape(fn(b)), S["cell"])
        except Exception:
            return P("n/a", S["cell"])

    def lat(k):
        return lambda b: f'p50 {b["api"][k]["p50_ms"]:.0f} ms, p95 {b["api"][k]["p95_ms"]:.0f} ms' + (f', {b["api"][k]["errors"]} errors' if "errors" in b["api"][k] else "")

    def conc(b):
        c = b["api"]["chat_concurrent_10_users"]
        return f'p50 {c["p50_ms"]:.0f} ms, p95 {c["p95_ms"]:.0f} ms, {c["throughput_rps"]} req/s, {c["errors"]} errors'

    def ing(b):
        i = b["api"]["ingestion"]
        return f'{i["file_mb"]} MB -> {i["chunks"]:,} chunks in {i["seconds"]} s ({i["chunks_per_sec"]:.0f}/s)'

    def mem(b):
        a = b["api"]
        return f'{a["api_rss_mb_idle"]} MB idle -> {a["api_rss_mb_after_load"]} MB after load' if a.get("api_rss_mb_idle") else "not measured (API in Docker)"

    def ret(scale):
        def f(b):
            r = b["retrieval"][str(scale)]
            return (f'HNSW p50 {r["dense_hnsw"]["p50_ms"]:.1f} / p95 {r["dense_hnsw"]["p95_ms"]:.1f} ms; exact {r["dense_exact_scan"]["p50_ms"]:.1f} ms; '
                    f'recall@10 {r["hnsw_recall_at_10"]:.2f}; keyword p50 {r["sparse_gin"]["p50_ms"]:.1f} ms')
        return f

    def env(b):
        e = b["environment"]
        return f'{e["platform"].split("-with")[0]}, {e["machine"]}, {e["cpu_count"]} vCPU/cores, {e.get("ram_gb", "?")} GB RAM, Python {e["python"]}'

    rows = [("Environment", env), ("Login (Argon2 hashing)", lat("login")), ("Chat, 40 sequential questions", lat("chat_sequential")),
            ("Chat, 10 simultaneous users", conc), ("Ingestion (test embedder)", ing), ("API process memory", mem),
            ("Retrieval at 5,000 chunks", ret(5000)), ("Retrieval at 20,000 chunks", ret(20000))]
    data = [[P("Measurement", S["cellb"]), P("Linux test VM (2 vCPU, 8 GB)", S["cellb"]), P("High-end: MacBook", S["cellb"])]]
    for name, fn in rows:
        data.append([P(f"<b>{name}</b>", S["cell"]), col(sb, fn), col(mac, fn)])
    return grid(data, widths)


def compat_table(inp, S, widths):
    data = [[P(x, S["cellb"]) for x in ("Browser / OS", "Version", "Result", "What was checked / notes")]]
    for r in inp["browser_matrix"]:
        data.append([P(ph(r["environment"]), S["cell"]), P(ph(r["version"]), S["cell"]), P(ph(r["result"]), S["cell"]), P(ph(r["notes"]), S["cell"])])
    return grid(data, widths)


# ----------------------------------------------------------------------------- documents
def build_technical_report(inp, bench, out):
    S = styles(7.9)
    NumberedCanvas.footer = "Company RAG Chatbot - Technical Report (Final Version)"
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=1.4 * cm, rightMargin=1.4 * cm, topMargin=1.2 * cm, bottomMargin=1.3 * cm,
                            title="Company RAG Chatbot - Technical Report", author=inp["author"] if not is_ph(inp["author"]) else "")
    W = A4[0] - 2.8 * cm
    rows = resolved_scope(inp)
    n = scope_summary(rows)
    lines = [loc(["backend/app"], {".py"}), loc(["frontend/src"], {".ts", ".tsx"}), loc(["backend/tests"], {".py"}), loc(["db"], {".sql"})]
    el = []

    el.append(P(escape(inp["title"]), S["title"]))
    meta = (f'<b>Author:</b> {ph(inp["author"])} &nbsp; <b>ID:</b> {ph(inp["student_id"])} &nbsp; <b>Programme:</b> {ph(inp["programme"])} &nbsp; '
            f'<b>Supervisor:</b> {ph(inp["supervisor"])} &nbsp; <b>Date:</b> {ph(inp["date"])}')
    el.append(P(meta, S["small"]))
    L = inp["links"]
    el.append(P(f'<b>Repository:</b> {ph(L["repository"])} &nbsp; <b>Walkthrough video:</b> {ph(L["video"])} &nbsp; <b>This report:</b> {ph(L["report"])}', S["small"]))

    el.append(P("1. Introduction", S["h1"]))
    el.append(P("The <b>Company RAG Chatbot</b> is a multi-tenant web platform that lets employees ask questions about their own company's documents, in English and "
                "Kinyarwanda, and receive grounded natural-language answers from a large language model. It has three roles: the <b>SuperAdmin</b> (platform owner: global RAG "
                "settings, API keys, review of company requests, platform analytics), the <b>Company Admin</b> (employees, documents, start/pause/end of the service, analytics, "
                "exports) and the <b>Employee</b> (chat, ratings, reports). Stack: Next.js 14 and React 18, FastAPI (Python 3.12), PostgreSQL 16 with pgvector, Google Gemini "
                "(gemini-3.8-flash for answers, gemini-embedding-2 for embeddings), Docker. Sections: scope alignment (2), technical functionality (3), testing (4), "
                "performance and compatibility (5), code quality (6), limitations (7).", S["body"]))

    el.append(P("2. Scope alignment and feature validation", S["h1"]))
    el.append(P(f'Planned features come from the project description, roadmap and the supervisor feedback. Result: <font color="{STATUS_COLOR[C.COMPLETED]}"><b>{n[C.COMPLETED]} completed</b></font>, '
                f'<font color="{STATUS_COLOR[C.PARTIAL]}"><b>{n[C.PARTIAL]} partial</b></font>, <font color="{STATUS_COLOR[C.MISSING]}"><b>{n[C.MISSING]} not implemented</b></font> '
                f'(of {len(rows)} features). Path legend: B: = backend/app/, F: = frontend/src/app/, T: = backend/tests/.', S["body"]))
    el.append(scope_table(rows, S, [W * 0.27, W * 0.22, W * 0.10, W * 0.41]))
    el.append(Spacer(1, 3))
    el.append(P("Scope changes and their justification", S["h2"]))
    el.append(changes_table(S, [W * 0.17, W * 0.45, W * 0.38]))

    el.append(P("3. Technical functionality", S["h1"]))
    el.append(architecture_drawing(W))
    el.append(P("Figure 1. Architecture. The browser talks to the API only through REST + JWT; every request sets a row-level-security context in PostgreSQL.", S["cap"]))
    el.append(P("<b>Front-end / back-end interaction.</b> The Next.js client calls a typed fetch wrapper (lib/api.ts) that adds the JWT and turns every failure into one error "
                "contract {code, message, fields}. Long jobs are polled (document progress every 2.5 s); downloads use authenticated blobs. Pydantic models validate all input, "
                "and form definitions, landing content, terms and languages are read from the database so they can change without a release.", S["body"]))
    el.append(P("<b>Ingestion pipeline (background worker).</b> Extract (pypdf, python-docx) -> clean (NFKC, unified apostrophes, hyphenation repair, repeated header/footer removal by "
                "line frequency across pages, soft-wrap merge) with EDA statistics -> language-aware chunking (parent-child, recursive or fixed; abbreviations, decimals and list "
                "numbers are protected; headings stay with their text; a chunk never mixes languages) -> batched embeddings with retry/back-off and pacing -> index "
                "(pgvector HNSW m=16, ef_construction=64; GIN full-text index). Jobs are claimed with FOR UPDATE SKIP LOCKED, so several workers cannot take the same job.", S["body"]))
    el.append(P("<b>Question answering.</b> Validate (service started, chat limit) -> detect language -> optional query transformation (short follow-ups get the previous question) -> embed -> "
                "<b>dense</b> search (cosine, HNSW) and <b>sparse</b> search (tsvector 'simple' + 'english', OR-query without stop-words) -> <b>Reciprocal Rank Fusion</b> "
                "(score = sum 1/(60 + rank)) -> evidence test (best dense similarity >= threshold) -> <b>parent expansion</b> (search small chunks, answer with the larger parent) -> prompt with an explicit "
                "language directive -> LLM -> store question, answer, scores, tokens, latency and the retrieved chunks for later auditing. Without evidence, the configured no-evidence prompt is used so company "
                "facts are never invented. Vectors from different embedding models are never compared; changing the model re-queues all documents.", S["body"]))
    el.append(P("<b>Multilingual support.</b> Languages are database rows (detection words, sample sentences). A stop-word-ratio detector with a confidence margin tags each paragraph and each "
                "question; unsure cases fall back to 'answer in the language of the question'. A built-in <i>Language check</i> embeds a translation pair and an unrelated sentence and reports whether "
                "cross-language matching works for the configured models. Kinyarwanda strings were written by the developer and need native review.", S["body"]))
    el.append(P("<b>Data handling and security.</b> 33 tables; JSONB for versioned configuration blocks; immutable versions of the terms with per-user acceptance records; API keys encrypted (Fernet), "
                "passwords hashed (Argon2), login throttling, parameterised SQL, CSV-formula neutralisation in exports. Company isolation is enforced three times: company_id on every record, "
                "backend scoping from the authenticated user, and PostgreSQL row-level security (FORCE, so it also binds the table owner). 'End service' runs six tracked, retryable steps "
                "(anonymise scores, vectors, database rows incl. employee accounts, files, temp files, logs).", S["body"]))
    el.append(P("<b>Company onboarding.</b> Applicant account -> request form (fields stored in the database) -> SuperAdmin approves, rejects with a comment or asks for information; messages "
                "appear in the portal and are queued as emails -> three walkthrough pages with versioned acceptance -> the company is created and the applicant becomes its admin.", S["body"]))

    el.append(P("4. Testing and validation", S["h1"]))
    data = [[P(x, S["cellb"]) for x in ("Strategy", "Why selected", "How conducted", "Results", "Improvements made afterwards")]]
    for a, b, c_, d_, e_ in C.TESTING:
        data.append([P(f"<b>{escape(a)}</b>", S["cell"]), P(escape(b), S["cell"]), P(escape(c_), S["cell"]), P(escape(d_), S["cell"]), P(escape(e_), S["cell"])])
    el.append(grid(data, [W * 0.12, W * 0.17, W * 0.30, W * 0.14, W * 0.27]))
    el.append(Spacer(1, 3))
    el.append(P("4.2 Testing with different inputs and error handling", S["h2"]))
    data = [[P(x, S["cellb"]) for x in ("Input / situation", "Expected behaviour", "Observed")]]
    for a, b, c_ in C.INPUTS:
        data.append([P(escape(a), S["cell"]), P(escape(b), S["cell"]), P(escape(expand(c_) if False else c_), S["cell"])])
    el.append(grid(data, [W * 0.31, W * 0.28, W * 0.41]))
    el.append(P("4.3 Live-model check (English / Kinyarwanda)", S["h2"]))
    el.append(P(ph(inp["language_check"]["summary"]), S["body"]))
    el.append(P("Test totals: <b>267 automated checks, all passing</b> (39 unit, 167 end-to-end integration, 32 REST, 29 browser); API statement coverage 84%, core-logic branch coverage 86%; plus the benchmark. Run: bash tests/run_all_tests.sh. Full evidence: docs/TESTING_REPORT.md.", S["body"]))

    el.append(P("5. Performance and compatibility", S["h1"]))
    el.append(P("The benchmark uses deterministic test AI models, so it measures the platform's own cost (HTTP, authentication, retrieval, database, ingestion) and <b>excludes Google's response "
                "time</b>, which dominates what a user perceives in production. The left column is a 2-vCPU, 8 GB Linux test VM; the high-end column is filled by running tests/benchmark.py on the MacBook.", S["body"]))
    el.append(perf_table(bench, S, [W * 0.20, W * 0.43, W * 0.37]))
    if bench["sandbox"]:
        chart = DOCS / "figures" / "performance.png"
        chart.parent.mkdir(exist_ok=True)
        performance_chart(bench["sandbox"], chart)
        el.append(Spacer(1, 2))
        el.append(Image(str(chart), width=W, height=W * 1.85 / 7.1))
        rr = bench["sandbox"]["retrieval"]
        rec = " and ".join(f'{rr[k]["hnsw_recall_at_10"]:.2f} at {int(k):,}' for k in sorted(rr, key=int))
        el.append(P("Figure 2. Measured on the Linux test VM (2 vCPU). HNSW and exact scan are equally fast at these sizes (a few milliseconds), so the index only pays off at larger scale and is kept for growth. "
                    f"Recall@10 of HNSW against exact search on random vectors (a worst case, no cluster structure) is {rec} chunks with the default ef_search; raising ef_search trades speed for recall.", S["cap"]))
    el.append(P("Front-end build (production): 21 routes, 87.3 kB shared JavaScript, 88-146 kB first-load per page; all pages are statically prerendered except two dynamic routes. "
                "Unit test runtime: about 1 s for 39 tests.", S["body"]))
    el.append(P("5.2 Software compatibility", S["h2"]))
    el.append(compat_table(inp, S, [W * 0.27, W * 0.14, W * 0.12, W * 0.47]))

    allshots = sorted(p_ for p_ in (DOCS / "screenshots").glob("*.png"))
    shots = [p_ for p_ in allshots if p_.name[:2] in ("04", "05", "06")] or allshots[:3]   # one row of three keeps the report within 5 pages
    if shots:
        from reportlab.lib.utils import ImageReader
        cw = (W - 8) / 3
        cells, row = [], []
        for p_ in shots:
            iw, ih = ImageReader(str(p_)).getSize()
            cap = p_.stem.lstrip("0123456789_").replace("_", " ")
            row.append([Image(str(p_), width=cw - 6, height=(cw - 6) * ih / iw), P(escape(cap), S["small"])])
            if len(row) == 3:
                cells.append(row); row = []
        if row:
            cells.append(row + [""] * (3 - len(row)))
        t = Table([[ [c[0], c[1]] if c else "" for c in r] for r in cells], colWidths=[cw + 2.7] * 3)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
        el.append(P("Figure 3. Key screens of the running application.", S["h2"]))
        el.append(t)
    else:
        el.append(P(ph("[Add 4-6 PNG screenshots to docs/screenshots (landing, request form, review, RAG configuration, documents, chat, analytics) and rebuild: they appear here as Figure 3.]"), S["body"]))

    el.append(P("6. Code quality and technical implementation", S["h1"]))
    el.append(P(f"<b>Structure and separation of concerns.</b> Backend: routers (HTTP only) -> services (business logic) -> rag/ (pipeline components) -> db helpers, with schemas, settings and "
                f"security in their own modules; no monolithic script. Front-end: pages, shared UI primitives, layout shell, API client and auth context. Size: backend {lines[0]:,} lines, front-end {lines[1]:,}, "
                f"tests {lines[2]:,}, SQL {lines[3]:,}; 109 API operations; 33 tables.", S["body"]))
    el.append(P("<b>OOP and SOLID, honestly stated.</b> Encapsulation: Detector (language data and logic), provider classes keep keys and settings private. Abstraction and polymorphism: "
                "GoogleEmbedder / FakeEmbedder and GoogleLLM / FakeLLM expose the same methods (embed, generate) and are created by factories (get_embedder, get_llm), so the chat and ingestion code "
                "never depends on a vendor; the fake classes replace the real ones in every test (Liskov substitution). Inheritance: Pydantic configuration models, an exception hierarchy "
                "(AIError -> RateLimitError), ApiError in the client. Open/closed: new query transforms, providers and languages are added through registries, factories or database rows without editing callers. "
                "Dependency inversion and composition: FastAPI dependencies (tenant(), role_user()) inject the authenticated user and a row-level-security-scoped connection. The pipeline stages are plain functions "
                "by design; interfaces are duck-typed rather than formal abstract classes, which would be a natural next refinement.", S["body"]))
    el.append(P("<b>Algorithms and problem solving.</b> Reciprocal Rank Fusion; HNSW approximate nearest-neighbour search; parent-child retrieval; recursive splitter with overlap and boundary protection; "
                "stop-word-ratio language detection with margin; header/footer detection by cross-page line frequency; exponential back-off and rate-limit pacing; FOR UPDATE SKIP LOCKED work queue; "
                "Argon2 hashing and login throttling; connection-pool-aware request design (found by load testing).", S["body"]))
    el.append(P("<b>Maintainability.</b> Consistent naming (snake_case Python, camelCase TypeScript), docstrings on non-obvious modules, idempotent SQL migration verified against a fresh install "
                "(identical columns, indexes, constraints), configuration through environment variables, secrets never in the repository, README, RUN_LOCALLY.md, DATABASE.md, Swagger and a Postman collection.", S["body"]))

    el.append(P("7. Limitations and future work", S["h1"]))
    el.append(P("Not done or limited: cloud deployment status as shown in Section 2; no OCR for scanned PDFs; no streaming of answers; no reranking model; email is outbound only; backups and retention rely on "
                "the hosting provider; login throttling and file storage are per instance (a multi-instance deployment needs shared storage and a shared counter); the free tier of the Gemini API may use submitted "
                "content to improve Google products, so a billing-enabled key is required for real company data; Kinyarwanda quality depends on the models and needs native review. "
                "Future work (supervisor): billing per usage, image understanding, marketing emails.", S["body"]))
    doc.build(el, canvasmaker=NumberedCanvas)
    return doc


def build_scope_pdf(inp, out):
    S = styles(8.6)
    NumberedCanvas.footer = "Company RAG Chatbot - Scope Alignment & Feature Validation"
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.4 * cm, bottomMargin=1.4 * cm, title="Scope Alignment and Feature Validation")
    W = A4[0] - 3.0 * cm
    rows = resolved_scope(inp)
    n = scope_summary(rows)
    el = [P("Scope Alignment &amp; Feature Validation", S["title"]),
          P(f'Project: {escape(inp["title"])}<br/>Author: {ph(inp["author"])} &nbsp; Supervisor: {ph(inp["supervisor"])} &nbsp; Date: {ph(inp["date"])}', S["small"]),
          Spacer(1, 4),
          P("How to read this document", S["h1"]),
          P("Every feature below was planned in the approved project description, the roadmap, or the supervisor feedback. <b>Completed</b> = implemented and covered by evidence; "
            "<b>Partial</b> = implemented in part, with the gap stated; <b>Not implemented</b> = not done. Evidence points to files in the repository (paths are relative to the repository root) and to the "
            "automated tests that exercise the feature. Screenshots of each screen are in docs/screenshots and are shown in the walkthrough video.", S["body"]),
          P(f'<b>Summary:</b> <font color="{STATUS_COLOR[C.COMPLETED]}"><b>{n[C.COMPLETED]} completed</b></font>, <font color="{STATUS_COLOR[C.PARTIAL]}"><b>{n[C.PARTIAL]} partial</b></font>, '
            f'<font color="{STATUS_COLOR[C.MISSING]}"><b>{n[C.MISSING]} not implemented</b></font> out of {len(rows)} planned features.', S["body"]),
          P("Feature validation table", S["h1"]),
          scope_table(rows, S, [W * 0.25, W * 0.20, W * 0.10, W * 0.45], expand_paths=True),
          P("Scope changes and justification", S["h1"]),
          changes_table(S, [W * 0.18, W * 0.44, W * 0.38]),
          P("Gaps that remain", S["h1"])]
    for _, feat, _, status, ev in rows:
        if status != C.COMPLETED:
            el.append(P(f"- <b>{escape(feat)}</b> ({escape(status)}): {escape(expand(ev))}", S["body"]))
    doc.build(el, canvasmaker=NumberedCanvas)


def write_scope_md(inp, out):
    rows = resolved_scope(inp)
    n = scope_summary(rows)
    esc = lambda t: t.replace("|", "\\|")
    md = ["# Scope Alignment & Feature Validation", "",
          f"**Project:** {inp['title']}  ", f"**Summary:** {n[C.COMPLETED]} completed, {n[C.PARTIAL]} partial, {n[C.MISSING]} not implemented (of {len(rows)} planned features).", "",
          "Status: **Completed** = implemented with evidence; **Partial** = implemented in part (gap stated); **Not implemented** = not done. "
          "Evidence paths are relative to the repository root.", "",
          "| Planned feature | Intended purpose | Status | Evidence |", "|---|---|---|---|"]
    for _, feat, purpose, status, ev in rows:
        md.append(f"| {esc(feat)} | {esc(purpose)} | **{status}** | {esc(expand(ev))} |")
    md += ["", "## Scope changes and justification", "", "| Change | What changed | Justification |", "|---|---|---|"]
    md += [f"| {esc(a)} | {esc(b)} | {esc(c)} |" for a, b, c in C.SCOPE_CHANGES]
    out.write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    inp, bench = load_inputs()
    if not bench["sandbox"]:
        sys.exit("docs/benchmark_results_sandbox.json is missing")
    build_technical_report(inp, bench, DOCS / "Technical_Report.pdf")
    build_scope_pdf(inp, DOCS / "Scope_Alignment_and_Feature_Validation.pdf")
    write_scope_md(inp, DOCS / "SCOPE_ALIGNMENT.md")
    from pypdf import PdfReader
    pages = len(PdfReader(str(DOCS / "Technical_Report.pdf")).pages)
    print(f"Technical_Report.pdf: {pages} pages" + ("  <-- OVER THE 5-PAGE LIMIT" if pages > 5 else "  (limit 5)"))
    print(f"Scope PDF: {len(PdfReader(str(DOCS / 'Scope_Alignment_and_Feature_Validation.pdf')).pages)} pages")
    todo = [k for k, v in {**{k: v for k, v in inp.items() if isinstance(v, str)}, **inp["links"]}.items() if is_ph(v)]
    print("Still to fill in report_inputs.json:", ", ".join(todo) or "nothing (check browser_matrix / language_check)")
