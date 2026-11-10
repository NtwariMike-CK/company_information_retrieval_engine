"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, CircleDashed, Download, Pause, Play, Trash2, TriangleAlert } from "lucide-react";
import { api, download, fmtDate } from "@/lib/api";
import { OverviewStats } from "@/components/stats";
import { Button, Card, ErrorText, Input, Modal, PageHeader, PageLoader, StatusBadge, useLoad, useToast } from "@/components/ui";

const STEPS = ["anonymize", "vectors", "database", "files", "temp_files", "logs"];
const STEP_LABEL: Record<string, string> = { anonymize: "Anonymous rating statistics (no names, no text)", vectors: "Chunks & embeddings", database: "Conversations, feedback, reports, employee accounts", files: "Uploaded files", temp_files: "Temporary files", logs: "Technical logs" };

export default function AdminDashboard() {
  const toast = useToast();
  const kb = useLoad<any>(() => api("/company/knowledge-base"));
  const overview = useLoad<any>(() => api("/company/analytics/overview"));
  const del = useLoad<any>(() => api("/company/service/deletion"));
  const [busy, setBusy] = useState("");
  const [endOpen, setEndOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [error, setError] = useState("");
  const [downloaded, setDownloaded] = useState(false);

  async function exportData() {
    setBusy("export"); setError("");
    try { await download("/company/export", "company-data-export.zip"); setDownloaded(true); toast("Your data was downloaded"); }
    catch (e: any) { setError(e.message); }
    setBusy("");
  }

  // poll while documents are processing or deletion is running
  useEffect(() => {
    const active = kb.data?.kb_status === "processing" || del.data?.status === "running" || del.data?.status === "pending";
    if (!active) return;
    const t = setInterval(() => { kb.reload(true); del.reload(true); }, 3000);
    return () => clearInterval(t);
  }, [kb.data, del.data]);

  async function act(action: "start" | "pause") {
    setBusy(action);
    try { await api(`/company/service/${action}`, { method: "POST" }); toast(action === "start" ? "Chatbot started. Employees can now ask questions." : "Chatbot paused. All data is preserved."); kb.reload(true); }
    catch (e: any) { toast(e.message, "err"); }
    setBusy("");
  }
  async function end() {
    setBusy("end"); setError("");
    try { await api("/company/service/end", { body: { confirm: "END" } }); setEndOpen(false); setConfirmText(""); toast("Deletion started"); kb.reload(true); del.reload(true); overview.reload(true); }
    catch (e: any) { setError(e.message); }
    setBusy("");
  }

  if (kb.loading || overview.loading) return <PageLoader />;
  const k = kb.data;
  const ready = k.kb_status === "ready";
  const d = del.data;
  const deleting = k.chatbot_state === "ended" && d && d.status !== "completed";

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Prepare the knowledge base, then start the assistant for your employees." />
      <Card className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className={`flex h-14 w-14 items-center justify-center rounded-full ${ready ? "bg-emerald-500/15 ring-2 ring-emerald-500/50" : k.kb_status === "failed" ? "bg-red-500/15 ring-2 ring-red-500/50" : "bg-ink-700 ring-2 ring-ink-600"}`}>
              {ready ? <CheckCircle2 className="h-7 w-7 text-emerald-400" /> : k.kb_status === "failed" ? <TriangleAlert className="h-7 w-7 text-red-400" /> : <CircleDashed className={`h-7 w-7 text-amber-300 ${k.kb_status === "processing" ? "animate-spin" : ""}`} />}
            </div>
            <div>
              <p className="text-lg font-semibold text-white">{ready ? "Knowledge base is ready" : k.kb_status === "processing" ? "Processing documents…" : k.kb_status === "failed" ? "Some documents failed" : "No documents yet"}</p>
              <div className="mt-1.5 flex items-center gap-2 text-sm text-slate-400">Chatbot: <StatusBadge status={k.chatbot_state} />
                {k.documents_by_status.map((s: any) => <span key={s.status} className="ml-2 text-xs">{s.n} {s.status}</span>)}</div>
              {!ready && k.kb_status !== "processing" && <Link href="/admin/documents" className="mt-1 inline-block text-sm text-brand-400 hover:underline">{k.kb_status === "failed" ? "Review failed documents →" : "Upload documents →"}</Link>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => act("start")} loading={busy === "start"} disabled={!k.can_start}><Play className="h-4 w-4" />{k.chatbot_state === "paused" ? "Resume" : "Start"}</Button>
            <Button variant="secondary" onClick={() => act("pause")} loading={busy === "pause"} disabled={k.chatbot_state !== "started"}><Pause className="h-4 w-4" />Pause</Button>
            <Button variant="danger" onClick={() => { setError(""); setEndOpen(true); }} disabled={k.chatbot_state === "ended" || (k.kb_status === "empty" && k.chatbot_state === "not_started")}><Trash2 className="h-4 w-4" />End service</Button>
          </div>
        </div>
        <p className="mt-4 border-t border-ink-700 pt-3 text-xs text-slate-500"><b className="text-slate-300">Start</b> lets employees chat. <b className="text-slate-300">Pause</b> blocks usage and keeps everything. <b className="text-slate-300">End</b> permanently deletes all documents, embeddings, conversations, feedback, reports and employee accounts.</p>
      </Card>

      {d && d.status && k.chatbot_state === "ended" && (
        <Card title="Deletion in progress" subtitle={`Started ${fmtDate(d.created_at)}`} className="mb-6" action={<StatusBadge status={d.status} />}>
          <ul className="space-y-2 text-sm">{STEPS.map((s) => (
            <li key={s} className="flex items-center gap-2">{d.steps[s] === "done" ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <CircleDashed className={`h-4 w-4 text-slate-500 ${deleting ? "animate-spin" : ""}`} />}<span className={d.steps[s] === "done" ? "text-slate-200" : "text-slate-400"}>{STEP_LABEL[s]}</span></li>))}</ul>
          {d.last_error && <div className="mt-3"><ErrorText>Last attempt failed and will be retried automatically (attempt {d.attempts}).</ErrorText></div>}
        </Card>)}
      {d && d.status === "completed" && k.chatbot_state === "not_started" && k.kb_status === "empty" && (
        <p className="mb-6 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">All company data was deleted on {fmtDate(d.completed_at)}. Upload and process documents again to restart the service.</p>)}

      {overview.data && <OverviewStats o={overview.data} />}

      <Modal open={endOpen} onClose={() => setEndOpen(false)} title="End service and delete all data">
        <div className="space-y-4">
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
            This permanently deletes uploaded documents, extracted text, chunks and embeddings, all conversations, feedback and reported cases, and <b>all employee accounts</b>. This cannot be undone. To use the service again you must re-create employees and re-upload documents.</div>
          <div className="rounded-lg border border-brand-500/30 bg-brand-500/10 p-3 text-sm text-slate-200">
            <p className="font-medium text-white">Download your data first</p>
            <p className="mt-1 text-slate-300">We recommend saving a copy: your original documents, conversations, questions, feedback and reports.</p>
            <Button variant="secondary" size="sm" className="mt-3" onClick={exportData} loading={busy === "export"}><Download className="h-3.5 w-3.5" />{downloaded ? "Download again" : "Download all my data (ZIP)"}</Button>
          </div>
          <p className="text-xs text-slate-500">Only anonymous rating scores and report categories (no names, company or text) are kept to improve the service.</p>
          <p className="text-sm text-slate-300">Type <b className="font-mono text-white">END</b> to confirm.</p>
          <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="END" autoFocus />
          <ErrorText>{error}</ErrorText>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setEndOpen(false)}>Cancel</Button><Button variant="danger" disabled={confirmText !== "END"} loading={busy === "end"} onClick={end}>Delete everything</Button></div>
        </div>
      </Modal>
    </>
  );
}
