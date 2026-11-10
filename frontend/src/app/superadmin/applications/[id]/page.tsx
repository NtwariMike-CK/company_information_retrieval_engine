"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Check, HelpCircle, Send, X } from "lucide-react";
import { api, fmtDate } from "@/lib/api";
import { StatusStepper, Thread } from "@/components/application";
import { Button, Card, ErrorText, Field, PageHeader, PageLoader, StatusBadge, Textarea, useLoad, useToast } from "@/components/ui";

export default function ApplicationReview() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const { data, loading, error, setData } = useLoad<any>(() => api(`/superadmin/applications/${id}`), [id]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  async function decide(action: "approve" | "reject" | "request_info") {
    if (action !== "approve" && comment.trim().length < 3) { setErr("Please write a comment for the applicant first."); return; }
    if (action === "reject" && !confirm("Reject this request? The applicant will see your comment and can submit a new request.")) return;
    setBusy(action); setErr("");
    try { const r = await api(`/superadmin/applications/${id}/decision`, { body: { action, comment } }); setData({ ...data, ...r }); setComment(""); toast(action === "approve" ? "Request approved" : action === "reject" ? "Request rejected" : "Information requested"); }
    catch (e: any) { setErr(e.message); }
    setBusy("");
  }
  async function send() {
    setBusy("msg"); setErr("");
    try { const r = await api(`/superadmin/applications/${id}/messages`, { body: { body: comment } }); setData({ ...data, ...r }); setComment(""); toast("Message sent"); }
    catch (e: any) { setErr(e.message); }
    setBusy("");
  }

  if (loading) return <PageLoader />;
  if (error || !data) return <ErrorText>{error || "Not found"}</ErrorText>;
  const open = ["pending", "needs_info"].includes(data.status);
  const canReject = open || data.status === "approved";
  return (
    <>
      <Link href="/superadmin/applications" className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />All requests</Link>
      <PageHeader title={data.company_name} subtitle={`Submitted ${fmtDate(data.submitted_at)}`} action={<StatusBadge status={data.status} />} />
      <Card className="mb-6"><StatusStepper status={data.status} /></Card>
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <Card title="Conversation"><Thread messages={data.messages} me="super_admin" /></Card>
          {canReject && (
            <Card title="Your decision" subtitle="Comments are shown to the applicant and emailed to them.">
              <div className="space-y-4">
                <Field label="Comment"><Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Required for “Request info” and “Reject”. Optional for “Approve”." /></Field>
                <ErrorText>{err}</ErrorText>
                <div className="flex flex-wrap gap-2">
                  {open && <Button onClick={() => decide("approve")} loading={busy === "approve"}><Check className="h-4 w-4" />Approve</Button>}
                  {open && <Button variant="secondary" onClick={() => decide("request_info")} loading={busy === "request_info"}><HelpCircle className="h-4 w-4" />Request more info</Button>}
                  <Button variant="danger" onClick={() => decide("reject")} loading={busy === "reject"}><X className="h-4 w-4" />Reject</Button>
                  <Button variant="ghost" onClick={send} loading={busy === "msg"} disabled={comment.trim().length < 2}><Send className="h-4 w-4" />Just send a message</Button>
                </div>
                {data.status === "approved" && <p className="text-xs text-slate-500">Approved: waiting for the applicant to finish onboarding and accept the terms. The company is created at that moment.</p>}
              </div>
            </Card>)}
        </div>
        <div className="space-y-6 lg:col-span-2">
          <Card title="Applicant">
            <dl className="space-y-2 text-sm"><div><dt className="text-xs uppercase text-slate-500">Name</dt><dd className="text-slate-200">{data.applicant.full_name}</dd></div>
              <div><dt className="text-xs uppercase text-slate-500">Email</dt><dd className="text-slate-200">{data.applicant.email}</dd></div>
              <div><dt className="text-xs uppercase text-slate-500">Phone</dt><dd className="text-slate-200">{data.applicant.phone}</dd></div></dl>
          </Card>
          <Card title="Company details">
            <dl className="space-y-3 text-sm">{data.fields.filter((f: any) => data.answers?.[f.key] !== undefined && data.answers[f.key] !== "").map((f: any) => (
              <div key={f.key}><dt className="text-xs uppercase tracking-wide text-slate-500">{f.label.replace(/ \(optional\)/, "")}</dt><dd className="mt-0.5 whitespace-pre-wrap text-slate-200">{Array.isArray(data.answers[f.key]) ? data.answers[f.key].join(", ") : String(data.answers[f.key])}</dd></div>))}</dl>
          </Card>
        </div>
      </div>
    </>
  );
}
