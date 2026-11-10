"use client";
import { useEffect, useState } from "react";
import { Download, FlaskConical, Pencil, Play, Plus, Trash2, Upload } from "lucide-react";
import { api, download, fmtDate } from "@/lib/api";
import { GroupedBars, LineChart, MetricCard, pct } from "@/components/charts";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Modal, PageHeader, PageLoader, Select, StatusBadge, Table, Tabs, Td, Textarea, useLoad, useToast } from "@/components/ui";

const P = "/superadmin/model-eval";
const MODE_LABEL: Record<string, string> = { oracle: "Gold context (tests the LLM alone)", pipeline: "End to end (real retrieval)", closed_book: "Baseline: no documents" };

export default function ModelEvalPage() {
  const [tab, setTab] = useState("run");
  return (
    <>
      <PageHeader title="Model evaluation" subtitle="Measure how well the embedding model, the retrieval pipeline and the LLM perform, with standard metrics, on a benchmark you control." />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "run", label: "Run & results" }, { id: "datasets", label: "Benchmark datasets" }, { id: "guide", label: "Metrics guide" }]} />
      {tab === "run" ? <RunTab /> : tab === "datasets" ? <DatasetsTab /> : <GuideTab />}
    </>
  );
}

/* ============================ run + results ============================ */
function RunTab() {
  const toast = useToast();
  const datasets = useLoad<any[]>(() => api(`${P}/datasets`));
  const runs = useLoad<any[]>(() => api(`${P}/runs`));
  const [form, setForm] = useState<any>({ dataset_id: "", kind: "retrieval", mode: "oracle", use_judge: true, pause_seconds: 0 });
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const active = runs.data?.some((r) => r.status === "queued" || r.status === "running");

  useEffect(() => { if (!form.dataset_id && datasets.data?.length) setForm((f: any) => ({ ...f, dataset_id: datasets.data![0].id })); }, [datasets.data]);
  useEffect(() => { if (!active) return; const t = setInterval(() => runs.reload(true), 2500); return () => clearInterval(t); }, [active]);

  async function start() {
    setBusy(true);
    try {
      const r = await api(`${P}/runs`, { body: { dataset_id: form.dataset_id, kind: form.kind, params: { mode: form.mode, use_judge: form.use_judge, pause_seconds: Number(form.pause_seconds) || 0 } } });
      toast("Evaluation started. It runs in the background."); runs.reload(true); setOpen(r.id);
    } catch (e: any) { toast(e.message, "err"); }
    setBusy(false);
  }
  const togglePick = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p.slice(-1), id]));
  const pair = picked.map((id) => runs.data?.find((r) => r.id === id)).filter(Boolean) as any[];

  return (
    <div className="space-y-6">
      <Card title="Start an evaluation" subtitle="Uses the ACTIVE RAG configuration. Benchmark documents are processed with your current cleaning, chunking and embedding settings.">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Benchmark dataset"><Select value={form.dataset_id} onChange={(e) => setForm({ ...form, dataset_id: e.target.value })}>{datasets.data?.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.cases} questions)</option>)}</Select></Field>
          <Field label="What to evaluate"><Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}><option value="retrieval">Embedding model and retrieval</option><option value="llm">LLM answers</option></Select></Field>
          <Field label="Pause between AI calls (seconds)" hint="Use about 12 on Google's free tier."><Input type="number" min={0} max={60} value={form.pause_seconds} onChange={(e) => setForm({ ...form, pause_seconds: e.target.value })} /></Field>
        </div>
        {form.kind === "llm" && (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field label="Context given to the LLM" hint="Gold context isolates the LLM from retrieval mistakes. Baseline shows what a plain chatbot would do."><Select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>{Object.entries(MODE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
            <label className="mt-6 flex items-center gap-3 text-sm"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={form.use_judge} onChange={(e) => setForm({ ...form, use_judge: e.target.checked })} />Use the LLM as judge (faithfulness, relevance). One extra call per question.</label>
          </div>)}
        <div className="mt-5 flex items-center justify-between gap-3 border-t border-ink-700 pt-4">
          <p className="text-xs text-slate-500">Real models make real API calls (about 1 per question, plus 1 for the judge).</p>
          <Button onClick={start} loading={busy} disabled={!form.dataset_id || active}><Play className="h-4 w-4" />{active ? "A run is in progress" : "Start evaluation"}</Button>
        </div>
      </Card>

      <Card title="Evaluation runs" subtitle="Tick two runs of the same type to compare them (for example before and after changing the chunk size or the embedding model)."
        action={pair.length === 2 && pair[0].kind === pair[1].kind ? <Badge tone="blue">comparing 2 runs below</Badge> : undefined}>
        {runs.loading ? <PageLoader /> : !runs.data?.length ? <Empty>No evaluations yet. Start one above.</Empty> : (
          <Table head={["", "When", "Dataset", "Type", "Models", "Status", "Headline", ""]}>
            {runs.data.map((r) => (
              <tr key={r.id} className={open === r.id ? "bg-ink-800/60" : "hover:bg-ink-800/40"}>
                <Td><input type="checkbox" className="accent-blue-500" checked={picked.includes(r.id)} disabled={r.status !== "completed"} onChange={() => togglePick(r.id)} aria-label="Select for comparison" /></Td>
                <Td>{fmtDate(r.created_at)}</Td><Td className="max-w-[12rem] text-xs">{r.dataset}</Td>
                <Td><Badge tone="blue">{r.kind === "retrieval" ? "Embedding + retrieval" : `LLM · ${r.params?.mode || "oracle"}`}</Badge></Td>
                <Td className="text-xs text-slate-400">{r.kind === "retrieval" ? r.embedding_model : r.llm_model}</Td>
                <Td>{r.status === "running" || r.status === "queued" ? <div className="w-36"><div className="mb-1 flex items-center justify-between"><StatusBadge status={r.status} /><span className="text-xs text-slate-400">{r.progress_pct}%</span></div><div className="h-1.5 overflow-hidden rounded-full bg-ink-700"><div className="h-full bg-brand-500 transition-all" style={{ width: `${r.progress_pct}%` }} /></div><p className="mt-1 truncate text-[11px] text-slate-500">{r.message}</p></div> : <div><StatusBadge status={r.status} />{r.error && <p className="mt-1 max-w-[14rem] text-[11px] text-red-300">{r.error}</p>}</div>}</Td>
                <Td className="text-xs">{r.status !== "completed" ? "-" : r.kind === "retrieval" ? `Hybrid Hit@5 ${pct(Number(r.hybrid_hit5))} · MRR ${Number(r.hybrid_mrr).toFixed(2)}` : `Key facts ${pct(Number(r.key_fact_recall))}${r.faithfulness ? ` · Faithful ${pct(Number(r.faithfulness))}` : ""}`}</Td>
                <Td><div className="flex justify-end gap-1"><Button variant="secondary" size="sm" disabled={r.status !== "completed"} onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? "Hide" : "View"}</Button>
                  <Button variant="ghost" size="sm" disabled={r.status === "running" || r.status === "queued"} onClick={async () => { if (confirm("Delete this run?")) { try { await api(`${P}/runs/${r.id}`, { method: "DELETE" }); if (open === r.id) setOpen(null); runs.reload(true); } catch (e: any) { toast(e.message, "err"); } } }}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button></div></Td>
              </tr>))}
          </Table>)}
      </Card>

      {pair.length === 2 && pair[0].kind === pair[1].kind && <Compare a={pair[0]} b={pair[1]} />}
      {open && <RunDetail key={open} id={open} />}
    </div>
  );
}

function RunDetail({ id }: { id: string }) {
  const run = useLoad<any>(() => api(`${P}/runs/${id}`), [id]);
  if (run.loading) return <PageLoader />;
  if (!run.data?.summary) return <Card title="Run"><Empty>{run.data?.status === "failed" ? run.data.error : "This run has no results yet."}</Empty></Card>;
  return run.data.kind === "retrieval" ? <RetrievalReport run={run.data} /> : <LLMReport run={run.data} />;
}

function ConfigCard({ run }: { run: any }) {
  const c = run.config_snapshot || {};
  const chunk = c.chunking || {}, r = c.retrieval || {};
  return (
    <Card title="Settings that were evaluated" subtitle={`Run of ${fmtDate(run.created_at)} on "${run.dataset}" (configuration version ${c.config_version})`}>
      <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Info k="Embedding model" v={`${c.embedding?.model} (${c.embedding?.dimensions}d, ${c.embedding?.provider})`} />
        <Info k="Chunking" v={chunk.strategy === "parent_child" ? `parent-child ${chunk.parent_size}/${chunk.child_size}, overlap ${chunk.overlap}` : `${chunk.strategy} ${chunk.chunk_size}, overlap ${chunk.overlap}`} />
        <Info k="Retrieval" v={`dense ${r.dense?.enabled ? "on" : "off"} · keyword ${r.sparse?.enabled ? "on" : "off"} · RRF k=${r.rrf_k} · top ${r.final_k} · threshold ${r.min_score}`} />
        <Info k="LLM" v={`${c.llm?.model} (${c.llm?.provider}), temperature ${c.llm?.temperature}`} />
      </div>
    </Card>
  );
}
const Info = ({ k, v }: { k: string; v: string }) => <div><p className="text-xs uppercase tracking-wide text-slate-500">{k}</p><p className="mt-0.5 text-slate-200">{v}</p></div>;

/* ---------------- embedding + retrieval report ---------------- */
function RetrievalReport({ run }: { run: any }) {
  const S = run.summary;
  const cases = useLoad<any[]>(() => api(`${P}/runs/${run.id}/cases`), [run.id]);
  const [sel, setSel] = useState<any | null>(null);
  const toast = useToast();
  const modes = S.modes || {};
  const d = modes.dense, h = modes.hybrid, sp = modes.sparse;
  const na = S.no_answer;
  const rows = [["Dense: embedding model alone", "dense", d], ["Keyword (BM25-style) baseline", "sparse", sp], ["Hybrid: dense + keyword (RRF), what the platform uses", "hybrid", h]].filter((x) => x[2]) as [string, string, any][];
  const best = (k: string) => Math.max(...rows.map((r) => r[2][k] ?? 0));
  const ev = S.evidence_integrity;

  return (
    <div className="space-y-6">
      <ConfigCard run={run} />
      <Card title="1. Embedding model quality" subtitle="Dense search only: does the embedding model rank the passage that contains the answer first? This isolates the embedding model from keyword search and fusion.">
        {d ? (<div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <MetricCard label="Hit@1" value={d["hit@1"]} ci={d["hit@1_ci95"]} sub="right passage ranked first" />
          <MetricCard label="Hit@5" value={d["hit@5"]} ci={d["hit@5_ci95"]} sub="right passage in top 5" />
          <MetricCard label="MRR" value={d.mrr} sub="mean reciprocal rank" />
          <MetricCard label="nDCG@10" value={d["ndcg@10"]} sub="ranking quality" />
          <MetricCard label="Precision@5" value={d["precision@5"]} sub="share of top 5 that are relevant (low is normal when few passages are relevant)" />
        </div>) : <Empty>Dense retrieval is disabled in the configuration.</Empty>}
        <p className="mt-3 text-xs text-slate-500">Evaluated on {S.n_evaluated} answerable questions whose evidence was found in a chunk. {S.n_unanswerable} unanswerable questions are used for the threshold analysis below.</p>
      </Card>

      <Card title="2. Retrieval method comparison" subtitle="Embedding-only and keyword-only are baselines. The hybrid method should be at least as good as the better of the two.">
        <Table head={["Method", "Hit@1", "Hit@5", "Hit@10", "MRR", "nDCG@10", "MAP", "Recall@5"]}>
          {rows.map(([label, key, m]) => (
            <tr key={key} className={key === "hybrid" ? "bg-brand-600/10" : ""}><Td className="font-medium text-white">{label}</Td>
              {["hit@1", "hit@5", "hit@10", "mrr", "ndcg@10", "map", "recall@5"].map((k) => <Td key={k} className={m[k] >= best(k) - 1e-9 ? "font-semibold text-emerald-300" : ""}>{pct(m[k], 1)}</Td>)}</tr>))}
        </Table>
        <div className="mt-5"><GroupedBars legend={[{ name: "Hit@5", color: "#3b82f6" }, { name: "MRR", color: "#93c5fd" }]} rows={rows.map(([label, , m]) => ({ label: label.split(":")[0], values: [{ name: "Hit@5", v: m["hit@5"], color: "#3b82f6" }, { name: "MRR", v: m.mrr, color: "#93c5fd" }] }))} /></div>
      </Card>

      <Card title="3. Cross-language retrieval" subtitle="Question language -> document language. Same-language pairs are the easy case; cross-language pairs test whether the embedding model maps meaning across English and Kinyarwanda.">
        <Table head={["Pair", "Questions", "Dense Hit@1", "Dense Hit@5", "Hybrid Hit@1", "Hybrid Hit@5", "Hybrid MRR"]}>
          {Object.entries(S.by_language_pair || {}).map(([k, v]: [string, any]) => (
            <tr key={k}><Td className="font-mono">{k}</Td><Td>{v.n}</Td><Td>{pct(v.dense?.["hit@1"])}</Td><Td>{pct(v.dense?.["hit@5"])}</Td><Td>{pct(v.hybrid?.["hit@1"])}</Td><Td>{pct(v.hybrid?.["hit@5"])}</Td><Td>{v.hybrid ? v.hybrid.mrr.toFixed(2) : "n/a"}</Td></tr>))}
        </Table>
        {S.cross_language_gap && <p className="mt-3 text-sm text-slate-300">Cross-language gap ({S.cross_language_gap.mode}): same-language Hit@5 <b>{pct(S.cross_language_gap.same_language_hit5 ?? S.cross_language_gap["same_language_hit@5"])}</b> versus cross-language <b>{pct(S.cross_language_gap["cross_language_hit@5"])}</b> (gap {pct(S.cross_language_gap.gap)}). A small gap means the embedding model handles both languages well.</p>}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="4. Cleaning and chunking health" subtitle="Did the pipeline keep the answer text intact?">
          <div className="grid grid-cols-2 gap-4">
            <MetricCard label="Evidence integrity" value={ev.value} ci={ev.ci95} sub="questions whose evidence survives inside one chunk" />
            <MetricCard label="Context recall (with parent)" value={S.context_recall.with_parent} sub={`child chunk only: ${pct(S.context_recall.child_only)}`} />
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-2 text-sm"><Info k="Chunks / parents" v={`${S.chunking_stats.chunks} / ${S.chunking_stats.parents}`} /><Info k="Chunk size (chars)" v={`median ${S.chunking_stats.median_chars}, p95 ${S.chunking_stats.p95_chars}`} /></dl>
          {ev.missing?.length > 0 && <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">Evidence was split across chunks (or lost) for: {ev.missing.join(" | ")}. Increase the chunk size or reduce overlap issues.</div>}
        </Card>
        <Card title="5. Speed" subtitle="Per question, on this server.">
          <dl className="grid grid-cols-2 gap-3 text-sm"><Info k="Embedding a question" v={S.latency.embed_ms_per_query === null ? "n/a" : `${S.latency.embed_ms_per_query} ms`} /><Info k="Dense search p50 / p95" v={`${S.latency.dense_ms_p50} / ${S.latency.dense_ms_p95} ms`} /><Info k="Keyword search p50 / p95" v={`${S.latency.sparse_ms_p50} / ${S.latency.sparse_ms_p95} ms`} /></dl>
        </Card>
      </div>

      <Card title="6. Does the knowledge base contain the answer? (evidence threshold)" subtitle="The platform answers 'I could not find it' when the best dense similarity is below the threshold. This sweep shows which threshold separates answerable from unanswerable questions best.">
        {!na.available ? <Empty>{na.reason}</Empty> : (<>
          <LineChart series={[{ name: "F1", color: "#3b82f6", points: na.curve.map((c: any) => [c.threshold, c.f1]) }, { name: "Precision", color: "#10b981", points: na.curve.map((c: any) => [c.threshold, c.precision]) }, { name: "Recall", color: "#f59e0b", points: na.curve.map((c: any) => [c.threshold, c.recall]) }]}
            vlines={[{ x: na.current_min_score, label: `current ${na.current_min_score}`, color: "#94a3b8" }, { x: na.suggested_min_score, label: `suggested ${na.suggested_min_score}`, color: "#3b82f6" }]} />
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <MetricCard label="F1 at current threshold" value={na.current.f1} sub={`precision ${pct(na.current.precision)} · recall ${pct(na.current.recall)}`} />
            <MetricCard label="F1 at suggested threshold" value={na.at_suggested.f1} sub={`precision ${pct(na.at_suggested.precision)} · recall ${pct(na.at_suggested.recall)}`} />
            <Info k="Average best similarity" v={`answerable ${na.mean_score_answerable}, unanswerable ${na.mean_score_unanswerable}`} />
          </div>
          <p className="mt-3 text-xs text-slate-500">To apply it: RAG Configuration, Retrieval tab, Evidence threshold. With very few questions the suggestion is rough; confirm it on a larger dataset. If the two average scores are close, the embedding model does not separate the cases well.</p>
        </>)}
      </Card>

      <Card title="7. Per-question results" action={<Button size="sm" variant="secondary" onClick={() => download(`${P}/runs/${run.id}/export`, "retrieval_evaluation.csv").catch((e: any) => toast(e.message, "err"))}><Download className="h-3.5 w-3.5" />CSV</Button>}>
        {cases.loading ? <PageLoader /> : (
          <Table head={["#", "Question", "Pair", "Answerable", "Hybrid: first relevant rank", "Dense: first relevant rank", "Best dense score", ""]}>
            {cases.data?.map((c, i) => {
              const rank = (k: string) => c.details[k]?.find((x: any) => x.relevant)?.rank;
              return (<tr key={c.id} className="hover:bg-ink-800/40"><Td>{i + 1}</Td><Td className="max-w-xs">{c.question}</Td><Td className="font-mono text-xs">{c.details.question_language}{c.details.document_language ? `->${c.details.document_language}` : ""}</Td>
                <Td>{c.metrics.answerable ? <Badge tone="green">yes</Badge> : <Badge>no</Badge>}</Td>
                <Td>{!c.metrics.answerable ? "-" : !c.metrics.evidence_located ? <Badge tone="amber">evidence split</Badge> : rank("hybrid") ? <Badge tone={rank("hybrid") <= 3 ? "green" : "amber"}>#{rank("hybrid")}</Badge> : <Badge tone="red">not in top 10</Badge>}</Td>
                <Td>{!c.metrics.answerable || !c.metrics.evidence_located ? "-" : rank("dense") ? `#${rank("dense")}` : "not in top 10"}</Td>
                <Td>{c.metrics.max_dense_score === null ? "n/a" : c.metrics.max_dense_score.toFixed(3)}</Td><Td><Button variant="ghost" size="sm" onClick={() => setSel(c)}>Details</Button></Td></tr>);
            })}
          </Table>)}
      </Card>
      <Modal wide open={!!sel} onClose={() => setSel(null)} title={sel?.question || ""}>
        {sel && <div className="space-y-4 text-sm">
          <p className="text-slate-400">Expected: <span className="text-slate-200">{sel.details.expected_answer || "-"}</span></p>
          {sel.details.evidence?.length > 0 && <p className="text-xs text-slate-500">Ground-truth evidence: {sel.details.evidence.join(" | ")}</p>}
          {["hybrid", "dense", "sparse"].map((mode) => (
            <div key={mode}><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{mode === "hybrid" ? "Hybrid (RRF)" : mode === "dense" ? "Dense (embedding)" : "Keyword"}: top results</p>
              {sel.details[mode].length === 0 ? <p className="text-xs text-slate-500">no results</p> : <div className="space-y-1">{sel.details[mode].slice(0, 5).map((x: any) => (
                <div key={x.chunk_id} className={`rounded-md border px-3 py-1.5 text-xs ${x.relevant ? "border-emerald-500/40 bg-emerald-500/10" : "border-ink-700 bg-ink-900"}`}><span className="mr-2 font-semibold text-white">#{x.rank}</span><span className="mr-2 text-slate-500">{x.source} · score {x.score}</span>{x.relevant && <Badge tone="green">relevant</Badge>}<p className="mt-0.5 text-slate-300">{x.text}</p></div>))}</div>}</div>))}
        </div>}
      </Modal>
    </div>
  );
}

/* ---------------- LLM report ---------------- */
function LLMReport({ run }: { run: any }) {
  const S = run.summary;
  const cases = useLoad<any[]>(() => api(`${P}/runs/${run.id}/cases`), [run.id]);
  const [sel, setSel] = useState<any | null>(null);
  const toast = useToast();
  return (
    <div className="space-y-6">
      <ConfigCard run={run} />
      <Card title="LLM answer quality" subtitle={`Mode: ${MODE_LABEL[S.mode]}. ${S.judge ? "LLM-as-judge was used for faithfulness, relevance and abstention." : "No judge: abstention is detected from the wording of the answer."}`}>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <MetricCard label="Key-fact recall" value={S.key_fact_recall} sub="required facts present in the answer" />
          <MetricCard label="Fully correct answers" value={S.fully_correct_rate} sub="all required facts present" />
          <MetricCard label="Token F1" value={S.token_f1} sub="word overlap with the reference answer (a strict, rough measure)" />
          <MetricCard label="Faithfulness" value={S.faithfulness} sub={S.judge ? "claims supported by the context (judge)" : "needs the judge"} />
          <MetricCard label="Relevance" value={S.relevance} sub={S.judge ? "answers the question (judge, 0-5 scaled)" : "needs the judge"} />
          <MetricCard label="Language match" value={S.language_match.value} ci={S.language_match.ci95} sub={`answered in the question's language (n=${S.language_match.n})`} />
          <MetricCard label="Abstention accuracy" value={S.abstention_accuracy.value} ci={S.abstention_accuracy.ci95} sub={`says "not found" when the answer is not in the documents (n=${S.abstention_accuracy.n})`} />
          <MetricCard label="False abstention rate" value={S.false_abstention_rate.value} goodHigh={false} sub="refuses although the answer exists (lower is better)" />
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-4"><Info k="Latency p50 / p95" v={`${S.latency.p50_ms} / ${S.latency.p95_ms} ms`} /><Info k="Tokens (in / out)" v={`${S.tokens.prompt} / ${S.tokens.completion}`} /><Info k="Questions scored" v={`${S.n_scored} of ${S.n_cases}${S.n_errors ? ` (${S.n_errors} errors)` : ""}`} /><Info k="Answerable / unanswerable" v={`${S.n_answerable} / ${S.n_unanswerable}`} /></dl>
        {S.mode === "closed_book" && <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">Baseline run: the model did not see the documents. Compare these numbers with a Gold-context or End-to-end run to see what retrieval adds.</p>}
      </Card>
      <Card title="By question language">
        <Table head={["Language", "Questions", "Key-fact recall", "Token F1", "Language match", "Faithfulness"]}>
          {Object.entries(S.by_language || {}).map(([k, v]: [string, any]) => <tr key={k}><Td className="font-mono">{k}</Td><Td>{v.n}</Td><Td>{pct(v.key_fact_recall)}</Td><Td>{pct(v.token_f1)}</Td><Td>{pct(v.language_match)}</Td><Td>{pct(v.faithfulness)}</Td></tr>)}
        </Table>
      </Card>
      <Card title="Per-question results" action={<Button size="sm" variant="secondary" onClick={() => download(`${P}/runs/${run.id}/export`, "llm_evaluation.csv").catch((e: any) => toast(e.message, "err"))}><Download className="h-3.5 w-3.5" />CSV</Button>}>
        {cases.loading ? <PageLoader /> : (
          <Table head={["#", "Question", "Answerable", "Key facts", "Token F1", "Faithful", "Abstained", ""]}>
            {cases.data?.map((c, i) => (<tr key={c.id} className="hover:bg-ink-800/40"><Td>{i + 1}</Td><Td className="max-w-xs">{c.question}</Td><Td>{c.metrics.answerable ? <Badge tone="green">yes</Badge> : <Badge>no</Badge>}</Td>
              <Td>{c.metrics.error ? <Badge tone="red">error</Badge> : c.metrics.key_fact_recall === undefined ? "-" : pct(c.metrics.key_fact_recall)}</Td><Td>{c.metrics.token_f1 === undefined ? "-" : pct(c.metrics.token_f1)}</Td>
              <Td>{c.metrics.faithfulness === undefined ? "-" : pct(c.metrics.faithfulness)}</Td><Td>{c.metrics.abstained === undefined ? "-" : c.metrics.abstained ? <Badge tone={c.metrics.answerable ? "red" : "green"}>yes</Badge> : <Badge tone={c.metrics.answerable ? "green" : "red"}>no</Badge>}</Td><Td><Button variant="ghost" size="sm" onClick={() => setSel(c)}>Details</Button></Td></tr>))}
          </Table>)}
      </Card>
      <Modal wide open={!!sel} onClose={() => setSel(null)} title={sel?.question || ""}>
        {sel && <div className="space-y-3 text-sm">
          {sel.details.error ? <ErrorText>{sel.details.error}</ErrorText> : (<>
            <div><p className="text-xs uppercase text-slate-500">Model answer</p><p className="mt-1 whitespace-pre-wrap rounded-lg bg-ink-900 p-3 text-slate-200">{sel.details.answer}</p></div>
            <div><p className="text-xs uppercase text-slate-500">Reference answer</p><p className="mt-1 text-slate-300">{sel.details.expected_answer || "-"}</p></div>
            {sel.details.key_facts?.length > 0 && <div className="flex flex-wrap gap-2">{sel.details.key_facts.map((k: any) => <Badge key={k.fact} tone={k.found ? "green" : "red"}>{k.found ? "found" : "missing"}: {k.fact}</Badge>)}</div>}
            {sel.details.judge && <p className="text-xs text-slate-400">Judge: {sel.details.judge.claims_supported}/{sel.details.judge.claims_total} claims supported · relevance {sel.details.judge.relevance}/5 · abstained {String(sel.details.judge.abstained)}</p>}
            <p className="text-xs text-slate-500">Language detected in the answer: {sel.details.language_detected || "unsure"} (expected {sel.details.question_language})</p>
            {sel.details.contexts?.length > 0 && <div><p className="text-xs uppercase text-slate-500">Context given</p>{sel.details.contexts.map((c: any, i: number) => <p key={i} className="mt-1 rounded-md border border-ink-700 bg-ink-900 p-2 text-xs text-slate-300"><b>{c.source}</b>: {c.text}</p>)}</div>}</>)}
        </div>}
      </Modal>
    </div>
  );
}

/* ---------------- compare two runs ---------------- */
function Compare({ a, b }: { a: any; b: any }) {
  const A = useLoad<any>(() => api(`${P}/runs/${a.id}`), [a.id]);
  const B = useLoad<any>(() => api(`${P}/runs/${b.id}`), [b.id]);
  if (A.loading || B.loading || !A.data?.summary || !B.data?.summary) return null;
  const sa = A.data.summary, sb = B.data.summary;
  const defs: [string, (s: any) => number | null | undefined, boolean][] = a.kind === "retrieval"
    ? ["dense", "sparse", "hybrid"].flatMap((m) => [[`${m}: Hit@1`, (s: any) => s.modes?.[m]?.["hit@1"], true], [`${m}: Hit@5`, (s: any) => s.modes?.[m]?.["hit@5"], true], [`${m}: MRR`, (s: any) => s.modes?.[m]?.mrr, true], [`${m}: nDCG@10`, (s: any) => s.modes?.[m]?.["ndcg@10"], true]] as any).concat([["Evidence integrity", (s: any) => s.evidence_integrity?.value, true], ["No-answer F1 (current threshold)", (s: any) => s.no_answer?.current?.f1, true]] as any)
    : [["Key-fact recall", (s: any) => s.key_fact_recall, true], ["Fully correct", (s: any) => s.fully_correct_rate, true], ["Token F1", (s: any) => s.token_f1, true], ["Faithfulness", (s: any) => s.faithfulness, true], ["Relevance", (s: any) => s.relevance, true], ["Language match", (s: any) => s.language_match?.value, true], ["Abstention accuracy", (s: any) => s.abstention_accuracy?.value, true], ["False abstention rate", (s: any) => s.false_abstention_rate?.value, false]];
  const lab = (r: any) => `${fmtDate(r.created_at)} · ${a.kind === "retrieval" ? r.embedding_model : r.llm_model}`;
  return (
    <Card title="Comparison" subtitle="Run A is the older selection, B the newer. Green = improved, red = got worse.">
      <p className="mb-3 text-xs text-slate-400">A: {lab(a)} &nbsp;|&nbsp; B: {lab(b)}</p>
      <Table head={["Metric", "A", "B", "Change"]}>
        {defs.map(([name, get, goodHigh]) => {
          const x = get(sa), y = get(sb);
          const d = x == null || y == null ? null : y - x;
          const good = d === null ? null : goodHigh ? d > 0.0001 : d < -0.0001, bad = d === null ? null : goodHigh ? d < -0.0001 : d > 0.0001;
          return <tr key={name}><Td>{name}</Td><Td>{pct(x, 1)}</Td><Td>{pct(y, 1)}</Td><Td className={good ? "font-semibold text-emerald-300" : bad ? "font-semibold text-red-300" : "text-slate-400"}>{d === null ? "n/a" : `${d > 0 ? "+" : ""}${(d * 100).toFixed(1)} pts`}</Td></tr>;
        })}
      </Table>
    </Card>
  );
}

/* ============================ datasets ============================ */
const blankCase = { question: "", question_language: "en", document_language: "en", answerable: true, expected_answer: "", evidence: "", key_facts: "" };

function DatasetsTab() {
  const toast = useToast();
  const list = useLoad<any[]>(() => api(`${P}/datasets`));
  const [sel, setSel] = useState<string>("");
  const [newDs, setNewDs] = useState<any | null>(null);
  useEffect(() => { if (!sel && list.data?.length) setSel(list.data[0].id); }, [list.data]);
  async function create() {
    try { const r = await api(`${P}/datasets`, { body: newDs }); setNewDs(null); await list.reload(true); setSel(r.id); toast("Dataset created. Add documents and questions."); } catch (e: any) { toast(e.message, "err"); }
  }
  if (list.loading) return <PageLoader />;
  return (
    <div className="space-y-6">
      <Card title="Benchmark datasets" subtitle="A dataset is a set of documents plus questions with ground truth. Documents run through the real pipeline; each question lists the verbatim sentence that contains the answer."
        action={<Button size="sm" onClick={() => setNewDs({ name: "", description: "" })}><Plus className="h-3.5 w-3.5" />New dataset</Button>}>
        <div className="flex flex-wrap gap-2">{list.data?.map((d) => (
          <button key={d.id} onClick={() => setSel(d.id)} className={`rounded-lg border px-3 py-2 text-left text-sm transition ${sel === d.id ? "border-brand-500 bg-brand-600/20 text-white" : "border-ink-600 text-slate-300 hover:border-slate-400"}`}>
            <span className="font-medium">{d.name}</span>{d.is_starter && <span className="ml-2"><Badge tone="blue">starter</Badge></span>}<span className="block text-xs text-slate-500">{d.documents} documents · {d.cases} questions ({d.answerable_cases} answerable)</span></button>))}</div>
      </Card>
      {sel && <DatasetEditor key={sel} id={sel} onChanged={() => list.reload(true)} onDeleted={() => { setSel(""); list.reload(true); }} />}
      <Modal open={!!newDs} onClose={() => setNewDs(null)} title="New dataset">
        {newDs && <div className="space-y-4"><Field label="Name"><Input value={newDs.name} onChange={(e) => setNewDs({ ...newDs, name: e.target.value })} /></Field><Field label="Description"><Textarea className="min-h-[70px]" value={newDs.description} onChange={(e) => setNewDs({ ...newDs, description: e.target.value })} /></Field>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setNewDs(null)}>Cancel</Button><Button onClick={create} disabled={newDs.name.trim().length < 2}>Create</Button></div></div>}
      </Modal>
    </div>
  );
}

function DatasetEditor({ id, onChanged, onDeleted }: { id: string; onChanged: () => void; onDeleted: () => void }) {
  const toast = useToast();
  const ds = useLoad<any>(() => api(`${P}/datasets/${id}`), [id]);
  const [m, setM] = useState<any | null>(null);
  const [err, setErr] = useState("");
  const [lang, setLang] = useState("en");
  const [imp, setImp] = useState<any | null>(null);
  const refresh = () => { ds.reload(true); onChanged(); };
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    const form = new FormData(); Array.from(files).forEach((f) => form.append("files", f)); form.append("language", lang);
    try { const r = await api(`${P}/datasets/${id}/documents`, { form }); r.results.filter((x: any) => x.status !== "added").forEach((x: any) => toast(`${x.filename}: ${x.reason}`, "err")); refresh(); } catch (e: any) { toast(e.message, "err"); }
  }
  async function saveCase() {
    setErr("");
    const body = { question: m.question, question_language: m.question_language, document_language: m.answerable ? m.document_language || null : null, answerable: m.answerable, expected_answer: m.expected_answer || null,
      evidence: String(m.evidence || "").split("\n").map((x) => x.trim()).filter(Boolean), key_facts: String(m.key_facts || "").split("\n").map((x) => x.trim()).filter(Boolean) };
    try { if (m.id) await api(`${P}/cases/${m.id}`, { method: "PUT", body }); else await api(`${P}/datasets/${id}/cases`, { body }); setM(null); refresh(); } catch (e: any) { setErr(e.message); }
  }
  async function doImport() {
    setErr("");
    try { const body = JSON.parse(imp.text); const r = await api(`${P}/datasets/${id}/cases/import?replace=${imp.replace}`, { body }); toast(`${r.imported} questions imported`); setImp(null); refresh(); } catch (e: any) { setErr(e.message); }
  }
  if (ds.loading || !ds.data) return <PageLoader />;
  const d = ds.data;
  return (
    <>
      <Card title={d.name} subtitle={d.description || undefined} action={<Button variant="danger" size="sm" onClick={async () => { if (confirm("Delete this dataset, its documents, questions and all its runs?")) { try { await api(`${P}/datasets/${id}`, { method: "DELETE" }); onDeleted(); } catch (e: any) { toast(e.message, "err"); } } }}><Trash2 className="h-3.5 w-3.5" />Delete dataset</Button>}>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <Select className="w-44" value={lang} onChange={(e) => setLang(e.target.value)}><option value="en">Documents in English</option><option value="rw">Documents in Kinyarwanda</option><option value="sw">Documents in Swahili</option><option value="fr">Documents in French</option></Select>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-ink-600 bg-ink-800 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-ink-700"><Upload className="h-4 w-4" />Upload documents<input type="file" multiple hidden accept=".pdf,.docx,.txt,.md" onChange={(e) => { upload(e.target.files); e.target.value = ""; }} /></label>
          <span className="text-xs text-slate-500">PDF, DOCX, TXT, MD (max 10 MB each)</span>
        </div>
        {d.documents.length === 0 ? <Empty>No documents yet.</Empty> : (
          <Table head={["Document", "Language", "Size", "Processed with current settings", ""]}>
            {d.documents.map((x: any) => <tr key={x.id}><Td className="font-medium text-white">{x.filename}</Td><Td className="font-mono">{x.language || "-"}</Td><Td>{Math.max(1, Math.round(x.size_bytes / 1024))} KB</Td><Td>{x.processed ? <Badge tone="green">processed at least once</Badge> : <Badge>pending (processed at the next run)</Badge>}</Td>
              <Td><Button variant="ghost" size="sm" onClick={async () => { if (confirm(`Remove ${x.filename}?`)) { await api(`${P}/datasets/${id}/documents/${x.id}`, { method: "DELETE" }); refresh(); } }}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button></Td></tr>)}
          </Table>)}
      </Card>
      <Card title={`Questions with ground truth (${d.cases.length})`} subtitle="Evidence = a verbatim sentence from the document that contains the answer. It is matched against chunks, so it works with any chunking settings."
        action={<div className="flex gap-2"><Button size="sm" variant="secondary" onClick={() => download(`${P}/datasets/${id}/cases/export`, "eval_cases.json").catch((e: any) => toast(e.message, "err"))}><Download className="h-3.5 w-3.5" />Export JSON</Button>
          <Button size="sm" variant="secondary" onClick={() => { setErr(""); setImp({ text: "", replace: false }); }}><Upload className="h-3.5 w-3.5" />Import JSON</Button>
          <Button size="sm" onClick={() => { setErr(""); setM({ ...blankCase }); }}><Plus className="h-3.5 w-3.5" />Add question</Button></div>}>
        {d.cases.length === 0 ? <Empty>No questions yet.</Empty> : (
          <Table head={["#", "Question", "Pair", "Answerable", "Evidence", ""]}>
            {d.cases.map((c: any, i: number) => <tr key={c.id}><Td>{i + 1}</Td><Td className="max-w-md">{c.question}</Td><Td className="font-mono text-xs">{c.question_language}{c.document_language ? `->${c.document_language}` : ""}</Td><Td>{c.answerable ? <Badge tone="green">yes</Badge> : <Badge>no</Badge>}</Td><Td className="text-xs text-slate-400">{c.evidence.length} phrase(s), {c.key_facts.length} fact(s)</Td>
              <Td><div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => { setErr(""); setM({ ...c, evidence: c.evidence.join("\n"), key_facts: c.key_facts.join("\n"), expected_answer: c.expected_answer || "" }); }}><Pencil className="h-3.5 w-3.5" /></Button>
                <Button variant="ghost" size="sm" onClick={async () => { await api(`${P}/cases/${c.id}`, { method: "DELETE" }); refresh(); }}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button></div></Td></tr>)}
          </Table>)}
      </Card>
      <Modal wide open={!!m} onClose={() => setM(null)} title={m?.id ? "Edit question" : "New question"}>
        {m && <div className="space-y-4">
          <Field label="Question"><Textarea className="min-h-[70px]" value={m.question} onChange={(e) => setM({ ...m, question: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Question language"><Select value={m.question_language} onChange={(e) => setM({ ...m, question_language: e.target.value })}><option value="en">en</option><option value="rw">rw</option><option value="sw">sw</option><option value="fr">fr</option></Select></Field>
            <Field label="Document language"><Select value={m.document_language || ""} disabled={!m.answerable} onChange={(e) => setM({ ...m, document_language: e.target.value })}><option value="en">en</option><option value="rw">rw</option><option value="sw">sw</option><option value="fr">fr</option></Select></Field>
            <label className="mt-6 flex items-center gap-3 text-sm"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={m.answerable} onChange={(e) => setM({ ...m, answerable: e.target.checked })} />The documents contain the answer</label>
          </div>
          <Field label="Reference answer (optional, used for token F1)"><Input value={m.expected_answer} onChange={(e) => setM({ ...m, expected_answer: e.target.value })} /></Field>
          {m.answerable && <Field label="Evidence: verbatim sentence(s) from the document, one per line" hint="Copy the exact sentence that contains the answer."><Textarea value={m.evidence} onChange={(e) => setM({ ...m, evidence: e.target.value })} /></Field>}
          <Field label="Key facts a correct answer must contain, one per line" hint='Use | for alternatives, e.g.  25|twenty-five'><Textarea className="min-h-[70px]" value={m.key_facts} onChange={(e) => setM({ ...m, key_facts: e.target.value })} /></Field>
          <ErrorText>{err}</ErrorText>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setM(null)}>Cancel</Button><Button onClick={saveCase} disabled={m.question.trim().length < 3}>Save</Button></div>
        </div>}
      </Modal>
      <Modal wide open={!!imp} onClose={() => setImp(null)} title="Import questions (JSON)">
        {imp && <div className="space-y-4"><p className="text-xs text-slate-400">A JSON list. Each item: question, question_language, document_language, answerable, expected_answer, evidence (list), key_facts (list). Use Export JSON to see the format.</p>
          <Textarea className="min-h-[220px] font-mono text-xs" value={imp.text} onChange={(e) => setImp({ ...imp, text: e.target.value })} />
          <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={imp.replace} onChange={(e) => setImp({ ...imp, replace: e.target.checked })} />Replace all existing questions</label><ErrorText>{err}</ErrorText>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setImp(null)}>Cancel</Button><Button onClick={doImport} disabled={!imp.text.trim()}>Import</Button></div></div>}
      </Modal>
    </>
  );
}

/* ============================ metrics guide ============================ */
const GUIDE: { group: string; items: { name: string; what: string; formula: string; read: string }[] }[] = [
  { group: "Embedding and retrieval (information-retrieval metrics)", items: [
    { name: "Hit@k (success rate)", what: "Did at least one passage that contains the answer appear in the top k results?", formula: "share of questions with a relevant chunk in the top k", read: "Hit@5 of 85% or more is a good target: the LLM almost always receives the answer. Hit@1 shows how often the very first result is right." },
    { name: "Precision@k", what: "How many of the top k results are relevant?", formula: "relevant results in top k / k", read: "Low values are normal when only one or two chunks contain the answer (the maximum for k=5 is then 20-40%). Use Hit@k and MRR first." },
    { name: "Recall@k", what: "How many of all relevant chunks were found in the top k?", formula: "relevant found in top k / all relevant chunks", read: "Matters when the answer is spread over several chunks." },
    { name: "MRR (mean reciprocal rank)", what: "How high is the first correct result on average?", formula: "average of 1 / rank of the first relevant result", read: "1.0 = always first. 0.5 = typically second." },
    { name: "nDCG@10", what: "Ranking quality: relevant results should be near the top.", formula: "DCG / ideal DCG, with DCG = sum of 1 / log2(rank + 1) over relevant results", read: "1.0 = ideal ordering." },
    { name: "MAP", what: "Average precision over the whole ranking, averaged over questions.", formula: "mean of precision at each relevant rank", read: "Rewards getting all relevant chunks high." } ] },
  { group: "Pipeline health (cleaning, chunking, thresholds)", items: [
    { name: "Evidence integrity", what: "Does the answer sentence survive cleaning and chunking inside one chunk?", formula: "answerable questions whose evidence is intact in some chunk / answerable questions", read: "Should be close to 100%. Lower values mean chunks cut through answers: increase the chunk size or review cleaning." },
    { name: "Context recall (child vs parent)", what: "Does the text finally sent to the LLM contain the evidence?", formula: "evidence phrases found in the retrieved context / evidence phrases", read: "With parent-child chunking the parent value should be at least as high as the child-only value." },
    { name: "Evidence threshold analysis", what: "How well does 'best similarity >= threshold' separate answerable from unanswerable questions?", formula: "precision, recall and F1 of the answerable class for each threshold", read: "Choose the threshold with the best F1 (suggested value). It prevents invented answers (too low) and needless refusals (too high)." },
    { name: "Cross-language gap", what: "Difference in Hit@5 between same-language and cross-language questions.", formula: "same-language Hit@5 minus cross-language Hit@5", read: "A gap under 10-15 points indicates good multilingual embeddings." } ] },
  { group: "LLM answer quality", items: [
    { name: "Key-fact recall", what: "Does the answer contain the facts a correct answer must have?", formula: "required facts found in the answer / required facts ('a|b' = alternatives)", read: "Deterministic and cheap. The most reliable correctness signal when the gold context is given." },
    { name: "Token F1", what: "Word overlap between the answer and the reference answer.", formula: "harmonic mean of word precision and recall", read: "Strict and rough: a correct answer worded differently scores low. Use it for trends, not as the main score." },
    { name: "Faithfulness", what: "Are the claims in the answer supported by the given context? (judge)", formula: "supported claims / claims", read: "Close to 100% means the model does not add facts that are not in the documents." },
    { name: "Answer relevance", what: "Does the answer address the question? (judge, 0-5 scaled to 0-100%)", formula: "judge score / 5", read: "" },
    { name: "Language match", what: "Is the answer in the same language as the question?", formula: "answers detected in the question's language / answers with a detectable language", read: "Important for English and Kinyarwanda. Language detection can be unsure for very short answers (those are excluded)." },
    { name: "Abstention accuracy / false abstention", what: "Does the model say 'not found' when the documents lack the answer, and NOT say it when they have it?", formula: "abstained on unanswerable / unanswerable;  abstained on answerable / answerable", read: "Abstention accuracy should be near 100% and false abstention near 0%." } ] },
  { group: "Reading the numbers responsibly", items: [
    { name: "Confidence intervals (95% CI)", what: "Shows how uncertain a percentage is on a small dataset (Wilson interval).", formula: "", read: "With 17 questions a 90% score can really be anywhere from about 70% to 97%. Use 50+ questions for firm conclusions." },
    { name: "Judge bias", what: "The LLM judge is the same model family as the one being judged.", formula: "", read: "It can be lenient. Always read the deterministic metrics (key facts, language, F1) next to the judged ones, and spot-check some answers in the per-question view." },
    { name: "Test models", what: "If the active providers are the offline test models, numbers only prove the pipeline works.", formula: "", read: "Run the evaluation with the real Gemini models for any claim about quality." } ] },
];

function GuideTab() {
  return (
    <div className="space-y-6">
      {GUIDE.map((g) => (
        <Card key={g.group} title={g.group}>
          <div className="space-y-3">{g.items.map((i) => (
            <details key={i.name} className="rounded-lg border border-ink-700 bg-ink-900 px-4 py-3"><summary className="cursor-pointer text-sm font-medium text-white">{i.name}<span className="ml-2 text-xs font-normal text-slate-500">{i.what}</span></summary>
              <div className="mt-3 space-y-1.5 border-t border-ink-700 pt-3 text-sm">{i.formula && <p className="text-slate-300"><b className="text-slate-400">Formula: </b><code className="rounded bg-ink-700 px-1.5 py-0.5 text-xs">{i.formula}</code></p>}{i.read && <p className="text-slate-300"><b className="text-slate-400">How to read it: </b>{i.read}</p>}</div></details>))}</div>
        </Card>))}
      <p className="flex items-center gap-2 text-xs text-slate-500"><FlaskConical className="h-3.5 w-3.5" />Colour bands (green 80% and above, amber 60-80%, red below 60%) are rules of thumb, not standards.</p>
    </div>
  );
}
