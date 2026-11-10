"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, tokenStore } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import { Brand } from "@/components/shell";
import { Button, ErrorText, Field, Input } from "@/components/ui";
import { ShieldCheck } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { user, loading, refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (!loading && user) router.replace(homeFor(user.role)); }, [user, loading, router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const r = await api("/auth/login", { body: { email, password } });
      tokenStore.set(r.access_token);
      await refresh();
      router.replace(homeFor(r.user.role));
    } catch (err: any) { setError(err.message); }
    setBusy(false);
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex justify-center"><Brand /></div>
        <div className="rounded-2xl border border-ink-700 bg-ink-850/90 p-8 shadow-2xl backdrop-blur">
          <h1 className="text-xl font-semibold text-white">Welcome back</h1>
          <p className="mt-1 text-sm text-slate-400">Sign in to search your company's knowledge base.</p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field label="Email"><Input type="email" required autoFocus autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" /></Field>
            <Field label="Password"><Input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" /></Field>
            <ErrorText>{error}</ErrorText>
            <Button type="submit" loading={busy} className="w-full">Sign in</Button>
          </form>
        </div>
        <p className="mt-5 text-center text-sm text-slate-400">New company? <Link href="/register" className="font-medium text-brand-400 hover:underline">Request access</Link></p>
        <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-slate-500"><ShieldCheck className="h-3.5 w-3.5" />Your company's data is isolated and never shared with other companies.</p>
      </div>
    </div>
  );
}
