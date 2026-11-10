"use client";
import { api } from "@/lib/api";
import { Markdown } from "@/components/markdown";
import { SiteFooter, SiteNav } from "@/components/marketing";
import { PageLoader, useLoad } from "@/components/ui";

export default function LegalPage() {
  const { data, loading } = useLoad<any[]>(() => api("/public/legal"));
  return (
    <div className="min-h-screen">
      <SiteNav />
      <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <h1 className="text-3xl font-semibold text-white">Privacy &amp; terms</h1>
        <p className="mt-2 text-sm text-slate-400">What every company administrator reads and accepts before a workspace is opened.</p>
        {loading ? <PageLoader /> : (
          <div className="mt-8 space-y-10">{data?.map((s) => (
            <article key={s.step_id} className="rounded-2xl border border-ink-700 bg-ink-850/70 p-6 sm:p-8">
              <p className="mb-4 text-xs uppercase tracking-wider text-brand-400">{s.title} · version {s.version}</p><Markdown>{s.body_markdown}</Markdown></article>))}</div>)}
      </main>
      <SiteFooter />
    </div>
  );
}
