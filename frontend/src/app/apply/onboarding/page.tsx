"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ArrowRight, Check, Lock } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Markdown } from "@/components/markdown";
import { Button, Card, cx, ErrorText, PageLoader, useLoad } from "@/components/ui";

export default function OnboardingPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const { data, loading, error } = useLoad<any[]>(() => api("/apply/onboarding"));
  const [i, setI] = useState(0);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (loading) return <PageLoader />;
  if (error || !data) return (
    <Card><div className="flex flex-col items-center gap-3 py-8 text-center"><Lock className="h-8 w-8 text-slate-500" /><p className="text-slate-300">{error || "Onboarding is not available yet."}</p>
      <p className="text-sm text-slate-500">It opens after your request is approved.</p><Link href="/apply"><Button variant="secondary">Back to my request</Button></Link></div></Card>);

  const step = data[i];
  const last = i === data.length - 1;

  async function finish() {
    setBusy(true); setErr("");
    try {
      await api("/apply/onboarding/complete", { body: { accepted: data!.map((s) => ({ step_id: s.step_id, version_id: s.version_id })) } });
      await refresh();
      router.replace("/admin");
    } catch (e: any) { setErr(e instanceof ApiError ? e.message : "Something went wrong."); }
    setBusy(false);
  }

  return (
    <>
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-brand-400">Step 3 of 3 · Onboarding</p>
        <h1 className="mt-1 text-2xl font-semibold text-white">Welcome! Let's get your workspace ready</h1>
      </div>
      <ol className="mb-6 grid gap-3 sm:grid-cols-3">
        {data.map((s, n) => (
          <li key={s.step_id} className={cx("flex items-center gap-3 rounded-xl border px-4 py-3 text-sm", n === i ? "border-brand-500/60 bg-brand-600/15 text-white" : n < i ? "border-emerald-500/30 bg-emerald-500/5 text-slate-300" : "border-ink-700 bg-ink-850 text-slate-500")}>
            <span className={cx("flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold", n < i ? "bg-emerald-500/25 text-emerald-300" : n === i ? "bg-brand-600 text-white" : "bg-ink-700")}>{n < i ? <Check className="h-4 w-4" /> : n + 1}</span>
            <span>Page {n + 1}: {s.title}</span></li>))}
      </ol>
      <Card>
        <h2 className="mb-5 text-xl font-semibold text-white">{step.title}</h2>
        <div className="max-h-[55vh] overflow-y-auto pr-2"><Markdown>{step.body_markdown}</Markdown></div>
        <div className="mt-6 space-y-4 border-t border-ink-700 pt-5">
          {step.requires_acceptance && (
            <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-ink-600 bg-ink-900 p-4 text-sm text-slate-200">
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-blue-500" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
              <span>I have read and accept the <b>{step.title}</b> (version {step.version}) on behalf of my company.</span></label>)}
          <ErrorText>{err}</ErrorText>
          <div className="flex items-center justify-between">
            <Button variant="ghost" disabled={i === 0} onClick={() => { setI(i - 1); setAgreed(false); }}><ArrowLeft className="h-4 w-4" />Back</Button>
            {last ? <Button onClick={finish} loading={busy} disabled={step.requires_acceptance && !agreed}>Accept &amp; open my workspace<ArrowRight className="h-4 w-4" /></Button>
              : <Button onClick={() => { setI(i + 1); setAgreed(false); }} disabled={step.requires_acceptance && !agreed}>Accept &amp; continue<ArrowRight className="h-4 w-4" /></Button>}
          </div>
        </div>
      </Card>
    </>
  );
}
