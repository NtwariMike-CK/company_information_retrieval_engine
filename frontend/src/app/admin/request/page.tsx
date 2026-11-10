"use client";
import { api, fmtDate } from "@/lib/api";
import { Thread } from "@/components/application";
import { Markdown } from "@/components/markdown";
import { Badge, Card, Empty, ErrorText, PageHeader, PageLoader, StatusBadge, useLoad } from "@/components/ui";

export default function RequestPage() {
  const { data, loading, error } = useLoad<any>(() => api("/company/request"));
  if (loading) return <PageLoader />;
  if (error) return <ErrorText>{error}</ErrorText>;
  const app = data.application;
  if (!app) return (
    <>
      <PageHeader title="Company request" subtitle="The request you submitted to join the platform." />
      <Empty>Your workspace was created directly by the platform team, so there is no online request on file.</Empty>
    </>);
  return (
    <>
      <PageHeader title="Company request" subtitle={`${app.company_name} · submitted ${fmtDate(app.submitted_at)}`} action={<StatusBadge status={app.status} />} />
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <Card title="History with the review team"><Thread messages={app.messages} me="applicant" /></Card>
          <Card title="Terms and pages you accepted" subtitle="Each acceptance is recorded with its version and date.">
            <div className="space-y-3">{data.accepted_terms.map((t: any) => (
              <details key={t.key + t.version} className="rounded-lg border border-ink-700 bg-ink-900 px-4 py-3">
                <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 text-sm text-white"><span>{t.title}</span><span className="flex items-center gap-2 text-xs text-slate-400"><Badge tone="blue">v{t.version}</Badge>accepted {fmtDate(t.accepted_at)}</span></summary>
                <div className="mt-4 border-t border-ink-700 pt-4"><Markdown>{t.body_markdown}</Markdown></div></details>))}</div>
          </Card>
        </div>
        <Card title="What you told us" className="h-fit lg:col-span-2">
          <dl className="space-y-3 text-sm">{data.fields.filter((f: any) => app.answers?.[f.key] !== undefined && app.answers[f.key] !== "").map((f: any) => (
            <div key={f.key}><dt className="text-xs uppercase tracking-wide text-slate-500">{f.label.replace(/ \(optional\)/, "")}</dt><dd className="mt-0.5 text-slate-200">{Array.isArray(app.answers[f.key]) ? app.answers[f.key].join(", ") : String(app.answers[f.key])}</dd></div>))}</dl>
        </Card>
      </div>
    </>
  );
}
