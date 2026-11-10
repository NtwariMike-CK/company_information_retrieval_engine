"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, tokenStore } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import { Brand } from "@/components/shell";
import { Button, ErrorText, Field, Input } from "@/components/ui";
import { CheckCircle2 } from "lucide-react";

const STEPS = ["Create your account", "Tell us about your company", "We review your request"];

export default function RegisterPage() {
  const router = useRouter();
  const { user, loading, refresh } = useAuth();
  const [f, setF] = useState({ full_name: "", phone: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: any) => setF({ ...f, [k]: e.target.value });
  useEffect(() => { if (!loading && user) router.replace(homeFor(user.role)); }, [user, loading, router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (f.password !== f.confirm) { setError("The two passwords do not match."); return; }
    setBusy(true); setError("");
    try {
      const r = await api("/public/register", { body: { full_name: f.full_name, phone: f.phone, email: f.email, password: f.password } });
      tokenStore.set(r.access_token);
      await refresh();
      router.replace("/apply");
    } catch (err: any) { setError(err.message); }
    setBusy(false);
  }

  return (
    <div className="min-h-screen px-4 py-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-10 flex items-center justify-between"><Link href="/"><Brand /></Link><Link href="/login" className="text-sm text-slate-400 hover:text-white">Already have an account? Sign in</Link></div>
        <div className="grid gap-10 lg:grid-cols-2">
          <div className="hidden lg:block">
            <h1 className="text-4xl font-semibold leading-tight text-white">Bring your company's knowledge to every employee</h1>
            <p className="mt-4 text-slate-400">Create an account, then tell us about your company. Our team reviews each request and replies right here in the portal and by email.</p>
            <ol className="mt-8 space-y-4">{STEPS.map((s, i) => (
              <li key={s} className="flex items-center gap-3"><span className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ${i === 0 ? "bg-brand-600 text-white shadow-glow" : "bg-ink-700 text-slate-400"}`}>{i + 1}</span><span className={i === 0 ? "font-medium text-white" : "text-slate-400"}>{s}</span></li>))}</ol>
            <ul className="mt-8 space-y-2 text-sm text-slate-400">{["English and Kinyarwanda", "Your data is isolated from every other company", "Delete everything with one click when you leave"].map((t) => <li key={t} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-400" />{t}</li>)}</ul>
          </div>
          <div className="rounded-2xl border border-ink-700 bg-ink-850/90 p-8 shadow-2xl">
            <p className="text-xs font-semibold uppercase tracking-wider text-brand-400">Step 1 of 3</p>
            <h2 className="mt-1 text-xl font-semibold text-white">Create your account</h2>
            <p className="mt-1 text-sm text-slate-400">You will be the administrator of your company's workspace.</p>
            <form onSubmit={submit} className="mt-6 space-y-4">
              <Field label="Full name"><Input required value={f.full_name} onChange={set("full_name")} autoComplete="name" /></Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Phone"><Input required value={f.phone} onChange={set("phone")} placeholder="+250…" autoComplete="tel" /></Field>
                <Field label="Email"><Input required type="email" value={f.email} onChange={set("email")} autoComplete="email" /></Field>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Password" hint="At least 8 characters"><Input required type="password" minLength={8} value={f.password} onChange={set("password")} autoComplete="new-password" /></Field>
                <Field label="Confirm password"><Input required type="password" minLength={8} value={f.confirm} onChange={set("confirm")} autoComplete="new-password" /></Field>
              </div>
              <ErrorText>{error}</ErrorText>
              <Button type="submit" loading={busy} className="w-full">Create account &amp; continue</Button>
              <p className="text-center text-xs text-slate-500">By continuing you agree to be contacted about your request. You will review the full terms before your workspace opens.</p>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
