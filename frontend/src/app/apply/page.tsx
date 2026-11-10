"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, PartyPopper, RotateCcw, Send } from "lucide-react";
import { api, ApiError, fmtDate } from "@/lib/api";
import { DynamicForm, FormField, StatusStepper, Thread } from "@/components/application";
import { Badge, Button, Card, ErrorText, Field, PageHeader, PageLoader, StatusBadge, Textarea, useLoad, useToast } from "@/components/ui";

export default function ApplyPage() {
  const toast = useToast();
  const state = useLoad<any>(() => api("/apply/state"));
  const form = useLoad<FormField[]>(() => api("/apply/form"));
  const [values, setValues] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState("");
  const [editAnswers, setEditAnswers] = useState(false);

  const cur = state.data?.current;
  useEffect(() => {  // pre-fill from the previous request (rejected / needs info)
    if (cur && (cur.status === "rejected" || cur.status === "needs_info")) setValues(cur.answers || {});
  }, [cur?.id, cur?.status]);

  async function submit() {
    setBusy(true); setError(""); setErrors({});
    try {
      await api("/apply/applications", { body: { answers: values, resubmission_of: cur?.status === "rejected" ? cur.id : undefined } });
      toast("Request submitted. We will review it shortly."); state.reload(true);
    } catch (e: any) { if (e instanceof ApiError) { setErrors(e.fields); setError(e.message); } }
    setBusy(false);
  }
  async function respond() {
    setBusy(true); setError(""); setErrors({});
    try {
      await api(`/apply/applications/${cur.id}/respond`, { body: { message: reply, ...(editAnswers ? { answers: values } : {}) } });
      toast("Reply sent"); setReply(""); setEditAnswers(false); state.reload(true);
    } catch (e: any) { if (e instanceof ApiError) { setErrors(e.fields); setError(e.message); } }
    setBusy(false);
  }

  if (state.loading || form.loading) return <PageLoader />;
  if (state.error) return <ErrorText>{state.error}</ErrorText>;
  const canSubmit = state.data.can_submit;
  const history = (state.data.applications as any[]).filter((a) => a.id !== cur?.id);

  return (
    <>
      {canSubmit ? (
        <>
          <PageHeader title={cur?.status === "rejected" ? "Submit a new request" : "Request access for your company"}
            subtitle="Step 2 of 3: tell us about your company. Fields marked * are required." />
          {cur?.status === "rejected" && (
            <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm">
              <p className="font-medium text-red-200">Your previous request was not approved</p>
              <p className="mt-1 whitespace-pre-wrap text-red-100/90">{cur.decision_comment}</p>
              <p className="mt-2 text-xs text-red-200/70">Your answers are pre-filled below. Update them and submit again.</p>
            </div>)}
          <Card>
            <DynamicForm fields={form.data || []} values={values} onChange={setValues} errors={errors} />
            <div className="mt-6 space-y-3 border-t border-ink-700 pt-5"><ErrorText>{error}</ErrorText>
              <div className="flex items-center justify-between gap-3"><p className="text-xs text-slate-500">You can have one open request at a time.</p>
                <Button onClick={submit} loading={busy}><Send className="h-4 w-4" />Submit request</Button></div></div>
          </Card>
          {cur?.status === "rejected" && cur.messages?.length > 0 && <div className="mt-8"><h2 className="mb-3 text-sm font-semibold text-white">Previous conversation</h2><Thread messages={cur.messages} me="applicant" /></div>}
        </>
      ) : (
        <>
          <PageHeader title={cur.company_name} subtitle={`Submitted ${fmtDate(cur.submitted_at)}`} action={<StatusBadge status={cur.status} />} />
          <Card className="mb-6"><StatusStepper status={cur.status} /></Card>

          {cur.status === "approved" && (
            <div className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-emerald-500/30 bg-gradient-to-r from-emerald-500/15 to-transparent p-6">
              <div className="flex items-center gap-4"><PartyPopper className="h-8 w-8 text-emerald-300" /><div><p className="text-lg font-semibold text-white">Your request was approved!</p><p className="text-sm text-slate-300">Finish a short onboarding (3 pages) to open your workspace.</p></div></div>
              <Link href="/apply/onboarding"><Button>Start onboarding <ArrowRight className="h-4 w-4" /></Button></Link>
            </div>)}
          {cur.status === "pending" && <p className="mb-6 rounded-xl border border-ink-600 bg-ink-850 px-4 py-3 text-sm text-slate-300">Your request is waiting for review. You will get an email, and the answer will appear here.</p>}

          <div className="grid gap-6 lg:grid-cols-5">
            <div className="space-y-6 lg:col-span-3">
              <Card title="Conversation with the review team"><Thread messages={cur.messages} me="applicant" /></Card>
              {cur.status === "needs_info" && (
                <Card title="Reply to the review team" subtitle="They asked for more information.">
                  <div className="space-y-4">
                    <Field label="Your reply"><Textarea value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Write your answer…" /></Field>
                    <button className="flex items-center gap-1.5 text-sm text-brand-400 hover:underline" onClick={() => setEditAnswers(!editAnswers)}><RotateCcw className="h-3.5 w-3.5" />{editAnswers ? "Hide my answers" : "Also edit my answers"}</button>
                    {editAnswers && <DynamicForm fields={form.data || []} values={values} onChange={setValues} errors={errors} />}
                    <ErrorText>{error}</ErrorText>
                    <Button onClick={respond} loading={busy} disabled={reply.trim().length < 2}><Send className="h-4 w-4" />Send reply</Button>
                  </div>
                </Card>)}
            </div>
            <Card title="Your answers" className="h-fit lg:col-span-2">
              <dl className="space-y-3 text-sm">{(form.data || []).filter((f) => cur.answers?.[f.key] !== undefined && cur.answers[f.key] !== "").map((f) => (
                <div key={f.key}><dt className="text-xs uppercase tracking-wide text-slate-500">{f.label.replace(/ \(optional\)/, "")}</dt><dd className="mt-0.5 text-slate-200">{Array.isArray(cur.answers[f.key]) ? cur.answers[f.key].join(", ") : String(cur.answers[f.key])}</dd></div>))}</dl>
            </Card>
          </div>
        </>)}

      {history.length > 0 && (
        <div className="mt-10"><h2 className="mb-3 text-sm font-semibold text-white">Earlier requests</h2>
          <div className="space-y-2">{history.map((a) => <div key={a.id} className="flex items-center justify-between rounded-lg border border-ink-700 bg-ink-850 px-4 py-2.5 text-sm"><span className="text-slate-200">{a.company_name}</span><span className="flex items-center gap-3 text-xs text-slate-500">{fmtDate(a.submitted_at)}<StatusBadge status={a.status} /></span></div>)}</div></div>)}
    </>
  );
}
