"use client";
import { useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { OverviewStats, scoreText } from "@/components/stats";
import { Badge, Card, Empty, PageHeader, PageLoader, Select, StatusBadge, Table, Tabs, Td, useLoad, useToast } from "@/components/ui";

export default function SuperAnalytics() {
  const toast = useToast();
  const companies = useLoad<any[]>(() => api("/superadmin/companies"));
  const [cid, setCid] = useState("");
  const [tab, setTab] = useState("overview");
  const qs = cid ? `?company_id=${cid}` : "";
  const analytics = useLoad<any>(() => api(`/superadmin/analytics${qs}`), [cid]);
  const feedback = useLoad<any[]>(() => api(`/superadmin/analytics/feedback${qs}`), [cid]);
  const reports = useLoad<any[]>(() => api(`/superadmin/reports${qs}`), [cid]);

  async function setStatus(id: string, status: string) {
    try { await api(`/superadmin/reports/${id}`, { method: "PATCH", body: { status } }); reports.reload(true); } catch (e: any) { toast(e.message, "err"); }
  }
  return (
    <>
      <PageHeader title="Analytics & Reports" subtitle="Platform-wide, or filtered to a single company."
        action={<div className="w-64"><Select value={cid} onChange={(e) => setCid(e.target.value)}><option value="">All companies</option>{companies.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></div>} />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "overview", label: "Overview" }, { id: "questions", label: "Frequent questions" }, { id: "feedback", label: "Feedback" }, { id: "reports", label: "Reported cases" }]} />
      {tab === "overview" && (analytics.loading ? <PageLoader /> : analytics.data && (
        <div className="space-y-6">
          <OverviewStats o={analytics.data.overview} />
          {analytics.data.companies && (
            <Card title="Per company">
              <Table head={["Company", "Access", "Chatbot", "Questions", "No evidence", "Avg rating", "Open reports", "Failed docs"]}>
                {analytics.data.companies.map((c: any) => (
                  <tr key={c.id}><Td className="font-medium text-white">{c.name}</Td><Td><StatusBadge status={c.access_status} /></Td><Td><StatusBadge status={c.chatbot_state} /></Td>
                    <Td>{c.questions}</Td><Td>{c.no_evidence}</Td><Td>{c.avg_rating ?? "—"}</Td><Td>{c.open_reports}</Td><Td>{c.failed_documents}</Td></tr>))}
              </Table>
            </Card>)}
        </div>))}
      {tab === "questions" && (analytics.loading ? <PageLoader /> : !analytics.data?.top_questions.length ? <Empty>No questions asked yet.</Empty> : (
        <Table head={["Question", "Times asked", "Info found", "Not found", "Last asked"]}>
          {analytics.data.top_questions.map((q: any, i: number) => <tr key={i}><Td className="max-w-md">{q.question}</Td><Td>{q.times_asked}</Td><Td>{q.found_info}</Td><Td>{q.not_found}</Td><Td>{fmtDate(q.last_asked)}</Td></tr>)}
        </Table>))}
      {tab === "feedback" && (feedback.loading ? <PageLoader /> : !feedback.data?.length ? <Empty>No feedback yet.</Empty> : (
        <Table head={["When", "Company", "Employee", "Question asked", "Answer", "Evaluation", "Score"]}>
          {feedback.data.map((f) => <tr key={f.id}><Td>{fmtDate(f.created_at)}</Td><Td>{f.company}</Td><Td>{f.employee}</Td><Td className="max-w-[14rem]">{f.question}</Td><Td className="max-w-xs"><p className="line-clamp-3 text-slate-300">{f.answer}</p></Td><Td className="max-w-[12rem] text-xs">{f.evaluation_question}</Td><Td><Badge tone="blue">{scoreText(f)}</Badge></Td></tr>)}
        </Table>))}
      {tab === "reports" && (reports.loading ? <PageLoader /> : !reports.data?.length ? <Empty>No reported cases.</Empty> : (
        <Table head={["When", "Company", "Employee", "Type", "Comments", "Status"]}>
          {reports.data.map((r) => (
            <tr key={r.id}><Td>{fmtDate(r.created_at)}</Td><Td>{r.company}</Td><Td>{r.employee}</Td><Td><Badge tone="blue">{r.type.replace(/_/g, " ")}</Badge></Td>
              <Td className="max-w-sm"><p>{r.comments}</p>{r.question && <p className="mt-1 text-xs text-slate-500">Q: {r.question}</p>}</Td>
              <Td><Select className="w-32 py-1 text-xs" value={r.status} onChange={(e) => setStatus(r.id, e.target.value)}><option value="open">open</option><option value="in_review">in review</option><option value="resolved">resolved</option></Select></Td></tr>))}
        </Table>))}
    </>
  );
}
