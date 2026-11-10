"use client";
import { useState } from "react";
import { Download } from "lucide-react";
import { api, download, fmtDate } from "@/lib/api";
import { OverviewStats, scoreText } from "@/components/stats";
import { Badge, Button, Card, Empty, Modal, PageHeader, PageLoader, Select, StatusBadge, Table, Tabs, Td, useLoad, useToast } from "@/components/ui";

export default function CompanyAnalytics() {
  const toast = useToast();
  const [tab, setTab] = useState("overview");
  const overview = useLoad<any>(() => api("/company/analytics/overview"));
  const feedback = useLoad<any[]>(() => api("/company/analytics/feedback?limit=200"));
  const reports = useLoad<any[]>(() => api("/company/analytics/reports?limit=200"));
  const questions = useLoad<any[]>(() => api("/company/analytics/questions"));
  const convs = useLoad<any[]>(() => api("/company/conversations?limit=200"));
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<any | null>(null);

  const dl = (fn: () => Promise<void>) => fn().catch((e: any) => toast(e.message, "err"));
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  async function openConv(id: string) {
    try { setDetail(await api(`/company/conversations/${id}`)); } catch (e: any) { toast(e.message, "err"); }
  }
  async function setStatus(id: string, status: string) {
    try { await api(`/company/reports/${id}`, { method: "PATCH", body: { status } }); reports.reload(true); } catch (e: any) { toast(e.message, "err"); }
  }

  return (
    <>
      <PageHeader title="Analytics" subtitle="How employees use the assistant and how well it answers." />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "overview", label: "Overview" }, { id: "feedback", label: "Feedback" }, { id: "reports", label: "Reported cases" }, { id: "questions", label: "Questions" }, { id: "conversations", label: "Conversations" }]} />

      {tab === "overview" && (overview.loading ? <PageLoader /> : overview.data && <OverviewStats o={overview.data} />)}

      {tab === "feedback" && (feedback.loading ? <PageLoader /> : !feedback.data?.length ? <Empty>No feedback yet.</Empty> : (
        <Table head={["When", "Employee", "Question", "Chatbot response", "Evaluation question", "Score"]}>
          {feedback.data.map((f) => (
            <tr key={f.id} className="hover:bg-ink-800/50"><Td>{fmtDate(f.created_at)}</Td><Td>{f.employee}</Td><Td className="max-w-[14rem]">{f.question}</Td>
              <Td className="max-w-sm"><p className="line-clamp-4 text-slate-300">{f.answer}</p></Td><Td className="max-w-[12rem] text-xs text-slate-400">{f.evaluation_question}</Td><Td><Badge tone="blue">{scoreText(f)}</Badge></Td></tr>))}
        </Table>))}

      {tab === "reports" && (reports.loading ? <PageLoader /> : !reports.data?.length ? <Empty>No reported cases.</Empty> : (
        <Table head={["When", "Employee", "Type", "Comments", "Status"]}>
          {reports.data.map((r) => (
            <tr key={r.id}><Td>{fmtDate(r.created_at)}</Td><Td>{r.employee}</Td><Td><Badge tone="blue">{r.type.replace(/_/g, " ")}</Badge></Td>
              <Td className="max-w-md"><p>{r.comments}</p>{r.question && <p className="mt-1.5 text-xs text-slate-500">Question: {r.question}</p>}</Td>
              <Td><Select className="w-32 py-1 text-xs" value={r.status} onChange={(e) => setStatus(r.id, e.target.value)}><option value="open">open</option><option value="in_review">in review</option><option value="resolved">resolved</option></Select></Td></tr>))}
        </Table>))}

      {tab === "questions" && (
        <Card title="Questions asked" subtitle="Grouped by identical wording" action={<Button size="sm" variant="secondary" onClick={() => dl(() => download("/company/analytics/questions/export", "questions_report.csv"))}><Download className="h-3.5 w-3.5" />Download CSV</Button>}>
          {questions.loading ? <PageLoader /> : !questions.data?.length ? <Empty>No questions yet.</Empty> : (
            <Table head={["Question", "Times asked", "Information found", "Not found", "Last asked"]}>
              {questions.data.map((q, i) => (
                <tr key={i}><Td className="max-w-lg">{q.question}</Td><Td className="font-semibold text-white">{q.times_asked}</Td>
                  <Td>{q.information_present ? <Badge tone="green">found ×{q.found_info}</Badge> : <Badge tone="red">not present</Badge>}</Td><Td>{q.not_found}</Td><Td>{fmtDate(q.last_asked)}</Td></tr>))}
            </Table>)}
        </Card>)}

      {tab === "conversations" && (
        <Card title="Employee conversations" action={
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={!selected.length} onClick={() => dl(() => download("/company/conversations/export", "selected_conversations.csv", { conversation_ids: selected, format: "csv" }))}><Download className="h-3.5 w-3.5" />Selected ({selected.length})</Button>
            <Button size="sm" variant="secondary" onClick={() => dl(() => download("/company/conversations/export", "all_conversations.csv", { format: "csv" }))}><Download className="h-3.5 w-3.5" />All (CSV)</Button>
          </div>}>
          {convs.loading ? <PageLoader /> : !convs.data?.length ? <Empty>No conversations yet.</Empty> : (
            <Table head={["", "Employee", "First question", "Exchanges", "Avg score", "Last activity", ""]}>
              {convs.data.map((c) => (
                <tr key={c.id} className="hover:bg-ink-800/50">
                  <Td><input type="checkbox" className="accent-blue-500" checked={selected.includes(c.id)} onChange={() => toggle(c.id)} aria-label="Select conversation" /></Td>
                  <Td>{c.employee}<p className="text-xs text-slate-500">{c.email}</p></Td><Td className="max-w-sm">{c.title || "—"}</Td><Td>{c.exchange_count}</Td>
                  <Td>{c.avg_score ? <Badge tone="blue">{c.avg_score}</Badge> : "—"}</Td><Td>{fmtDate(c.updated_at)}</Td>
                  <Td><Button variant="ghost" size="sm" onClick={() => openConv(c.id)}>View</Button></Td></tr>))}
            </Table>)}
        </Card>)}

      <Modal wide open={!!detail} onClose={() => setDetail(null)} title={detail ? `${detail.employee} · ${fmtDate(detail.created_at)}` : ""}>
        {detail && <div className="space-y-4">
          {detail.messages.map((m: any) => m.role === "user" ? (
            <div key={m.id} className="ml-auto max-w-[85%] rounded-xl bg-brand-600/25 px-4 py-2.5 text-sm ring-1 ring-brand-500/30"><p className="mb-1 text-[11px] uppercase tracking-wide text-brand-300">Employee · Q{m.exchange_no}</p>{m.content}</div>
          ) : (
            <div key={m.id} className="max-w-[92%] rounded-xl border border-ink-700 bg-ink-900 px-4 py-3 text-sm">
              <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-slate-400">Assistant
                {m.has_evidence ? <Badge tone="green">evidence found</Badge> : <Badge tone="red">no evidence</Badge>}{m.latency_ms ? <span>{(m.latency_ms / 1000).toFixed(1)}s</span> : null}</div>
              <p className="whitespace-pre-wrap text-slate-200">{m.content}</p>
              {m.evidence.length > 0 && <p className="mt-2 text-xs text-slate-500">Retrieved from: {[...new Set(m.evidence.filter((e: any) => e.used_in_prompt).map((e: any) => e.filename))].join(", ") || "—"}</p>}
              {m.feedback.length > 0 && <div className="mt-2 flex flex-wrap gap-2">{m.feedback.map((f: any, i: number) => <span key={i} className="rounded-md bg-ink-800 px-2 py-1 text-xs text-slate-300">{f.question}: <b className="text-white">{scoreText(f)}</b></span>)}</div>}
            </div>))}
        </div>}
      </Modal>
    </>
  );
}
