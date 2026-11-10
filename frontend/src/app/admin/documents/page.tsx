"use client";
import { DragEvent, useEffect, useRef, useState } from "react";
import { FileText, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { api, fmtDate } from "@/lib/api";
import { Badge, Button, Card, Empty, Modal, PageHeader, PageLoader, StatusBadge, Table, Td, useLoad, useToast } from "@/components/ui";

const STAGES = ["extract", "clean", "chunk", "embed", "index"];
const size = (b: number) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

export default function DocumentsPage() {
  const toast = useToast();
  const docs = useLoad<any[]>(() => api("/company/documents"));
  const kb = useLoad<any>(() => api("/company/knowledge-base"));
  const [uploading, setUploading] = useState(false);
  const [drag, setDrag] = useState(false);
  const [eda, setEda] = useState<any | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const busy = docs.data?.some((d) => d.status === "uploaded" || d.status === "processing");
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => { docs.reload(true); kb.reload(true); }, 2500);
    return () => clearInterval(t);
  }, [busy]);

  async function upload(files: FileList | File[]) {
    if (!files.length) return;
    setUploading(true);
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    try {
      const r = await api("/company/documents", { form });
      const bad = r.results.filter((x: any) => x.status !== "queued");
      const good = r.results.length - bad.length;
      if (good) toast(`${good} document${good > 1 ? "s" : ""} queued for processing`);
      bad.forEach((b: any) => toast(`${b.filename}: ${b.reason}`, "err"));
      docs.reload(true); kb.reload(true);
    } catch (e: any) { toast(e.message, "err"); }
    setUploading(false);
    if (input.current) input.current.value = "";
  }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files); };
  async function remove(d: any) {
    if (!confirm(`Delete "${d.filename}" and its chunks and embeddings?`)) return;
    try { await api(`/company/documents/${d.id}`, { method: "DELETE" }); toast("Document deleted"); docs.reload(true); kb.reload(true); } catch (e: any) { toast(e.message, "err"); }
  }
  async function retry(d: any) {
    try { await api(`/company/documents/${d.id}/retry`, { method: "POST" }); docs.reload(true); } catch (e: any) { toast(e.message, "err"); }
  }
  const ended = kb.data?.chatbot_state === "ended";

  return (
    <>
      <PageHeader title="Knowledge base" subtitle="Upload company documents. Each file is extracted, cleaned, chunked, embedded and indexed in the background."
        action={kb.data && <div className="flex items-center gap-2 text-sm text-slate-400">Status: <StatusBadge status={kb.data.kb_status} /></div>} />
      <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
        onClick={() => !ended && input.current?.click()}
        className={`mb-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${ended ? "cursor-not-allowed opacity-50" : ""} ${drag ? "border-brand-500 bg-brand-500/10" : "border-ink-600 bg-ink-850/60 hover:border-brand-500/60"}`}>
        <UploadCloud className="h-9 w-9 text-brand-400" />
        <p className="mt-3 text-sm font-medium text-white">{uploading ? "Uploading…" : "Drop files here or click to browse"}</p>
        <p className="mt-1 text-xs text-slate-400">PDF, Word (.docx), TXT and Markdown · size limits are set by the platform administrator</p>
        <input ref={input} type="file" multiple hidden accept=".pdf,.docx,.txt,.md" onChange={(e) => e.target.files && upload(e.target.files)} />
      </div>
      {ended && <p className="mb-4 text-sm text-amber-300">Service data is being deleted. You can upload again once deletion completes.</p>}
      {docs.loading ? <PageLoader /> : !docs.data?.length ? <Empty>No documents uploaded yet.</Empty> : (
        <Table head={["Document", "Size", "Pipeline", "Chunks", "Uploaded", ""]}>
          {docs.data.map((d) => {
            const idx = STAGES.indexOf(d.stage);
            return (
              <tr key={d.id} className="hover:bg-ink-800/50">
                <Td><div className="flex items-start gap-2"><FileText className="mt-0.5 h-4 w-4 shrink-0 text-brand-400" /><div><p className="font-medium text-white">{d.filename}</p><Badge>{d.file_type}</Badge></div></div></Td>
                <Td>{size(d.size_bytes)}</Td>
                <Td className="min-w-[16rem]">
                  <div className="mb-1.5 flex items-center gap-2"><StatusBadge status={d.status} />{d.status === "processing" && <span className="text-xs capitalize text-slate-400">{d.stage}…</span>}</div>
                  {(d.status === "processing" || d.status === "uploaded") && <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700"><div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${d.progress_pct || 2}%` }} /></div>}
                  <div className="mt-1.5 flex gap-1">{STAGES.map((s, i) => <span key={s} className={`h-1 flex-1 rounded ${d.status === "ready" || i < idx ? "bg-emerald-500" : i === idx && d.status === "processing" ? "bg-brand-500" : "bg-ink-700"}`} title={s} />)}</div>
                  {d.status === "failed" && <p className="mt-1.5 text-xs text-red-300">{d.error_message}</p>}
                </Td>
                <Td>{d.chunks}</Td><Td>{fmtDate(d.created_at)}</Td>
                <Td><div className="flex justify-end gap-1">
                  {d.eda_stats && <Button variant="ghost" size="sm" onClick={() => setEda(d)}>EDA</Button>}
                  {d.status === "failed" && <Button variant="secondary" size="sm" onClick={() => retry(d)}><RefreshCw className="h-3.5 w-3.5" />Retry</Button>}
                  <Button variant="ghost" size="sm" disabled={d.status === "processing"} onClick={() => remove(d)}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button></div></Td>
              </tr>);
          })}
        </Table>)}
      <Modal open={!!eda} onClose={() => setEda(null)} title={`Document analysis · ${eda?.filename || ""}`}>
        {eda?.eda_stats && <div className="grid grid-cols-2 gap-3">{Object.entries(eda.eda_stats).map(([k, v]) => (
          <div key={k} className="rounded-lg border border-ink-700 bg-ink-900 p-3"><p className="text-xs uppercase tracking-wide text-slate-400">{k.replace(/_/g, " ")}</p><p className="mt-1 text-lg font-semibold text-white">{typeof v === "object" && v !== null ? Object.entries(v as Record<string, number>).map(([a, b]) => `${a}: ${b}`).join(", ") : String(v)}</p></div>))}</div>}
      </Modal>
    </>
  );
}
