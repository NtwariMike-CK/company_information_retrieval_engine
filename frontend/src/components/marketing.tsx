"use client";
import Link from "next/link";
import { ReactNode } from "react";
import { ArrowRight, BarChart3, Building2, CheckCircle2, ClipboardList, Database, FileText, Globe, KeyRound, Languages, Lock, MessageSquare, Rocket, Search, ShieldCheck, Sparkles, Trash2, UserCheck, Users, Zap } from "lucide-react";
import { homeFor, useAuth } from "@/lib/auth";
import { Brand } from "./shell";

const ICONS: Record<string, any> = { BarChart3, Building2, CheckCircle2, ClipboardList, Database, FileText, Globe, KeyRound, Languages, Lock, MessageSquare, Rocket, Search, ShieldCheck, Sparkles, Trash2, UserCheck, Users, Zap };
export const ICON_NAMES = Object.keys(ICONS);
export function Icon({ name, className }: { name?: string; className?: string }) {
  const C = (name && ICONS[name]) || Sparkles;
  return <C className={className} />;
}

export function SiteNav() {
  const { user } = useAuth();
  return (
    <header className="sticky top-0 z-30 border-b border-ink-700/70 bg-ink-950/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
        <Link href="/"><Brand /></Link>
        <nav className="hidden items-center gap-6 text-sm text-slate-400 md:flex">
          <a href="/#features" className="hover:text-white">Features</a>
          <a href="/#how_it_works" className="hover:text-white">How it works</a>
          <a href="/#languages" className="hover:text-white">Languages</a>
          <Link href="/legal" className="hover:text-white">Privacy &amp; terms</Link>
        </nav>
        <div className="flex items-center gap-2">
          {user ? (
            <Link href={homeFor(user.role)} className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-glow hover:bg-brand-500">Open dashboard</Link>
          ) : (<>
            <Link href="/login" className="rounded-lg px-3 py-2 text-sm font-medium text-slate-300 hover:text-white">Sign in</Link>
            <Link href="/register" className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-glow hover:bg-brand-500">Request access</Link>
          </>)}
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-ink-700 bg-ink-900/60">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-8 text-sm text-slate-500 sm:flex-row sm:px-6">
        <Brand />
        <div className="flex gap-5"><Link href="/legal" className="hover:text-white">Privacy &amp; terms</Link><Link href="/login" className="hover:text-white">Sign in</Link><Link href="/register" className="hover:text-white">Request access</Link></div>
        <p>© {new Date().getFullYear()} Company RAG Assistant</p>
      </div>
    </footer>
  );
}

export function Section({ id, title, subtitle, children, alt }: { id?: string; title?: string; subtitle?: string; children: ReactNode; alt?: boolean }) {
  return (
    <section id={id} className={`scroll-mt-16 py-16 sm:py-20 ${alt ? "bg-ink-900/50" : ""}`}>
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        {(title || subtitle) && (
          <div className="mx-auto mb-12 max-w-2xl text-center">
            {title && <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">{title}</h2>}
            {subtitle && <p className="mt-3 text-slate-400">{subtitle}</p>}
          </div>)}
        {children}
      </div>
    </section>
  );
}

export function CtaButtons() {
  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      <Link href="/register" className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-glow transition hover:bg-brand-500">Request access <ArrowRight className="h-4 w-4" /></Link>
      <Link href="/login" className="rounded-xl border border-ink-600 bg-ink-800/60 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:bg-ink-700">Sign in</Link>
    </div>
  );
}

/** Illustrative bilingual chat card shown next to the hero text. */
export function ChatMock() {
  return (
    <div className="relative mx-auto w-full max-w-md">
      <div className="absolute -inset-4 rounded-3xl bg-brand-600/20 blur-3xl" />
      <div className="relative space-y-4 rounded-2xl border border-ink-600 bg-ink-850/90 p-5 shadow-2xl">
        <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-slate-500"><span>Example conversation</span><span className="flex gap-1"><i className="h-2 w-2 rounded-full bg-slate-600" /><i className="h-2 w-2 rounded-full bg-slate-600" /><i className="h-2 w-2 rounded-full bg-brand-500" /></span></div>
        <div className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-sm text-white">Abakozi bemerewe iminsi ingahe y'ikiruhuko buri mwaka?</div></div>
        <div className="flex gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink-700"><Sparkles className="h-4 w-4 text-brand-300" /></div>
          <div className="text-sm leading-relaxed text-slate-200">Abakozi bemerewe iminsi makumyabiri n'itanu (25) y'ikiruhuko buri mwaka. <span className="text-brand-300">[1]</span>
            <div className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-ink-600 bg-ink-900 px-2 py-1 text-xs text-slate-300"><FileText className="h-3 w-3 text-brand-400" />HR-policy.pdf · p.4</div></div>
        </div>
        <div className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-sm text-white">Can I carry unused days over?</div></div>
        <div className="flex gap-3"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink-700"><Sparkles className="h-4 w-4 text-brand-300" /></div>
          <div className="text-sm text-slate-400">Searching company documents<span className="ml-1 inline-flex gap-0.5"><i className="dot h-1 w-1 rounded-full bg-slate-400" /><i className="dot h-1 w-1 rounded-full bg-slate-400" /><i className="dot h-1 w-1 rounded-full bg-slate-400" /></span></div></div>
      </div>
    </div>
  );
}
