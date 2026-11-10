"use client";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { api } from "@/lib/api";
import { ChatMock, CtaButtons, Icon, Section, SiteFooter, SiteNav } from "@/components/marketing";
import { Markdown } from "@/components/markdown";
import { PageLoader, useLoad } from "@/components/ui";

type Item = { title: string; text: string; icon?: string };
type Block = { key: string; label: string; content: { title: string; subtitle: string; body: string; items: Item[] } };

export default function Landing() {
  const { data, loading, error } = useLoad<Block[]>(() => api("/public/site-content"));
  const langs = useLoad<any[]>(() => api("/public/languages"));
  if (loading) return <PageLoader />;
  const blocks = data || [];
  const by = (k: string) => blocks.find((b) => b.key === k);
  const hero = by("hero");
  const known = new Set(["hero", "highlights", "features", "how_it_works", "languages", "security", "faq", "cta"]);

  return (
    <div className="min-h-screen">
      <SiteNav />
      {error && <p className="px-6 py-4 text-center text-sm text-red-300">{error}</p>}

      {hero && (
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(900px_400px_at_20%_-10%,rgba(37,99,235,0.28),transparent_60%)]" />
          <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:py-24">
            <div>
              {!!langs.data?.length && <div className="mb-5 inline-flex flex-wrap items-center gap-2 rounded-full border border-brand-500/30 bg-brand-500/10 px-3 py-1 text-xs font-medium text-brand-300">
                {langs.data.map((l) => l.name).join(" · ")}</div>}
              <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight text-white sm:text-5xl lg:text-6xl">{hero.content.title}</h1>
              <p className="mt-5 max-w-xl text-lg text-slate-400">{hero.content.subtitle}</p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link href="/register" className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-glow transition hover:bg-brand-500">Request access <ArrowRight className="h-4 w-4" /></Link>
                <Link href="/login" className="rounded-xl border border-ink-600 bg-ink-800/60 px-6 py-3 text-sm font-semibold text-slate-100 hover:bg-ink-700">Sign in</Link>
              </div>
              <p className="mt-4 text-xs text-slate-500">Every company request is reviewed by our team before access is granted.</p>
            </div>
            <ChatMock />
          </div>
        </section>)}

      {by("highlights") && (
        <div className="border-y border-ink-700 bg-ink-900/60">
          <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
            {by("highlights")!.content.items.map((it, i) => (
              <div key={i} className="flex items-start gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-600/20 ring-1 ring-brand-500/30"><Icon name={it.icon} className="h-5 w-5 text-brand-300" /></div>
                <div><p className="text-sm font-semibold text-white">{it.title}</p><p className="mt-0.5 text-xs text-slate-400">{it.text}</p></div></div>))}
          </div>
        </div>)}

      {by("features") && (
        <Section id="features" title={by("features")!.content.title} subtitle={by("features")!.content.subtitle}>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {by("features")!.content.items.map((it, i) => (
              <div key={i} className="group rounded-2xl border border-ink-700 bg-ink-850/70 p-6 transition hover:border-brand-500/50 hover:bg-ink-800">
                <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600/20 ring-1 ring-brand-500/30 transition group-hover:bg-brand-600/30"><Icon name={it.icon} className="h-5 w-5 text-brand-300" /></div>
                <h3 className="font-semibold text-white">{it.title}</h3><p className="mt-2 text-sm leading-relaxed text-slate-400">{it.text}</p></div>))}
          </div>
        </Section>)}

      {by("how_it_works") && (
        <Section id="how_it_works" alt title={by("how_it_works")!.content.title} subtitle={by("how_it_works")!.content.subtitle}>
          <ol className="grid gap-5 md:grid-cols-5">
            {by("how_it_works")!.content.items.map((it, i) => (
              <li key={i} className="relative rounded-2xl border border-ink-700 bg-ink-850/70 p-5">
                <span className="mb-3 flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white shadow-glow">{i + 1}</span>
                <h3 className="text-sm font-semibold text-white">{it.title}</h3><p className="mt-1.5 text-sm text-slate-400">{it.text}</p></li>))}
          </ol>
        </Section>)}

      {by("languages") && (
        <Section id="languages" title={by("languages")!.content.title} subtitle={by("languages")!.content.subtitle}>
          <div className="grid items-center gap-10 lg:grid-cols-2">
            <div className="space-y-4">
              <p className="text-slate-300">{by("languages")!.content.body}</p>
              <ul className="space-y-3">{by("languages")!.content.items.map((it, i) => (
                <li key={i} className="flex items-start gap-3 rounded-xl border border-ink-700 bg-ink-850/70 p-4"><Icon name={it.icon} className="mt-0.5 h-5 w-5 shrink-0 text-brand-400" />
                  <div><p className="text-sm font-medium text-white">{it.title}</p>{it.text && <p className="mt-0.5 text-sm text-slate-400">{it.text}</p>}</div></li>))}</ul>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {(langs.data || []).map((l) => (
                <div key={l.code} className="rounded-2xl border border-ink-700 bg-gradient-to-br from-ink-800 to-ink-850 p-6 text-center"><p className="text-3xl font-semibold text-white">{l.native_name}</p><p className="mt-1 text-sm text-slate-400">{l.name}</p></div>))}
            </div>
          </div>
        </Section>)}

      {by("security") && (
        <Section id="security" alt title={by("security")!.content.title} subtitle={by("security")!.content.subtitle}>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {by("security")!.content.items.map((it, i) => (
              <div key={i} className="rounded-2xl border border-ink-700 bg-ink-850/70 p-6"><Icon name={it.icon} className="mb-3 h-6 w-6 text-brand-400" /><h3 className="font-semibold text-white">{it.title}</h3><p className="mt-2 text-sm text-slate-400">{it.text}</p></div>))}
          </div>
          <p className="mt-8 text-center text-sm text-slate-400"><Link href="/legal" className="inline-flex items-center gap-1.5 text-brand-400 hover:underline"><Check className="h-4 w-4" />Read the privacy summary and terms</Link></p>
        </Section>)}

      {by("faq") && (
        <Section id="faq" title={by("faq")!.content.title} subtitle={by("faq")!.content.subtitle}>
          <div className="mx-auto max-w-3xl space-y-3">
            {by("faq")!.content.items.map((it, i) => (
              <details key={i} className="group rounded-xl border border-ink-700 bg-ink-850/70 px-5 py-4 open:border-brand-500/40">
                <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium text-white">{it.title}<span className="ml-4 text-brand-400 transition group-open:rotate-45">+</span></summary>
                <p className="mt-3 text-sm leading-relaxed text-slate-400">{it.text}</p></details>))}
          </div>
        </Section>)}

      {blocks.filter((b) => !known.has(b.key)).map((b) => (
        <Section key={b.key} id={b.key} title={b.content.title} subtitle={b.content.subtitle}>
          {b.content.body && <div className="mx-auto max-w-3xl"><Markdown>{b.content.body}</Markdown></div>}
          {b.content.items.length > 0 && <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{b.content.items.map((it, i) => (
            <div key={i} className="rounded-2xl border border-ink-700 bg-ink-850/70 p-6"><Icon name={it.icon} className="mb-3 h-6 w-6 text-brand-400" /><h3 className="font-semibold text-white">{it.title}</h3><p className="mt-2 text-sm text-slate-400">{it.text}</p></div>))}</div>}
        </Section>))}

      {by("cta") && (
        <section className="px-4 pb-20 sm:px-6">
          <div className="relative mx-auto max-w-4xl overflow-hidden rounded-3xl border border-brand-500/30 bg-gradient-to-br from-brand-700/40 via-ink-850 to-ink-900 px-6 py-14 text-center">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(500px_200px_at_50%_0%,rgba(59,130,246,0.25),transparent_70%)]" />
            <h2 className="relative text-3xl font-semibold text-white sm:text-4xl">{by("cta")!.content.title}</h2>
            <p className="relative mx-auto mt-3 max-w-xl text-slate-300">{by("cta")!.content.subtitle}</p>
            <div className="relative mt-8"><CtaButtons /></div>
          </div>
        </section>)}
      <SiteFooter />
    </div>
  );
}
