"use client";
import { Card, Empty, Stat, StatusBadge } from "./ui";

/** Overview cards + rating distribution used by both SuperAdmin and Company analytics. */
export function OverviewStats({ o }: { o: any }) {
  const total = o.answered_with_evidence + o.no_evidence;
  const dist: Record<number, number> = {};
  o.rating_distribution?.forEach((r: any) => (dist[r.rating] = Number(r.n)));
  const max = Math.max(1, ...Object.values(dist));
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Questions asked" value={o.questions} />
        <Stat label="Information found" value={total ? `${Math.round((o.answered_with_evidence / total) * 100)}%` : "—"} hint={`${o.no_evidence} answered without evidence`} />
        <Stat label="Avg rating" value={o.avg_rating ?? "—"} hint={`${o.rating_count} ratings`} />
        <Stat label="Avg response time" value={o.avg_latency_ms ? `${(o.avg_latency_ms / 1000).toFixed(1)}s` : "—"} />
        <Stat label="Conversations" value={o.conversations} />
        <Stat label="True / False" value={`${o.true_count} / ${o.false_count}`} hint="feedback answers" />
        <Stat label="Tokens (in / out)" value={`${Number(o.prompt_tokens).toLocaleString()} / ${Number(o.completion_tokens).toLocaleString()}`} />
        <Stat label="Open reports" value={o.reports_by_status?.find((r: any) => r.status === "open")?.n ?? 0} />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Rating distribution">
          {Object.keys(dist).length === 0 ? <Empty>No ratings yet.</Empty> : (
            <div className="space-y-2">{[5, 4, 3, 2, 1].map((r) => (
              <div key={r} className="flex items-center gap-3 text-sm"><span className="w-4 text-slate-400">{r}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-ink-700"><div className="h-full rounded-full bg-brand-500" style={{ width: `${((dist[r] || 0) / max) * 100}%` }} /></div>
                <span className="w-8 text-right text-slate-300">{dist[r] || 0}</span></div>))}</div>)}
        </Card>
        <Card title="Documents">
          {o.documents_by_status?.length ? <div className="space-y-2">{o.documents_by_status.map((d: any) => <div key={d.status} className="flex items-center justify-between"><StatusBadge status={d.status} /><span className="font-semibold text-white">{d.n}</span></div>)}</div> : <Empty>No documents.</Empty>}
        </Card>
        <Card title="Errors (30 days)">
          {o.errors_last_30_days?.length ? <div className="space-y-2">{o.errors_last_30_days.map((e: any, i: number) => <div key={i} className="flex items-center justify-between text-sm"><span>{e.source} <span className="font-mono text-xs text-slate-400">{e.error_code}</span></span><span className="font-semibold text-white">{e.n}</span></div>)}</div> : <Empty>No errors.</Empty>}
        </Card>
      </div>
    </div>
  );
}

export const scoreText = (r: any) => (r.rating != null ? `${r.rating} / 5` : r.bool_value ? "True" : "False");
