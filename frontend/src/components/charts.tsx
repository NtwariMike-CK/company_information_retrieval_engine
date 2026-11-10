"use client";
import { cx } from "./ui";

export const pct = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(d)}%`);
/** Rule-of-thumb colour bands (guidance, not a standard): >= 80% good, 60-80% fair, below 60% needs work. */
export const tone = (v: number | null | undefined, goodHigh = true) => {
  if (v === null || v === undefined) return "slate";
  const x = goodHigh ? v : 1 - v;
  return x >= 0.8 ? "green" : x >= 0.6 ? "amber" : "red";
};
const TXT: Record<string, string> = { green: "text-emerald-300", amber: "text-amber-300", red: "text-red-300", slate: "text-slate-300" };
const BAR: Record<string, string> = { green: "bg-emerald-500", amber: "bg-amber-400", red: "bg-red-500", slate: "bg-slate-500" };

export function MetricCard({ label, value, sub, ci, goodHigh = true, fmt }: { label: string; value: number | null | undefined; sub?: string; ci?: number[]; goodHigh?: boolean; fmt?: (v: number) => string }) {
  const t = tone(value, goodHigh);
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-850/80 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className={cx("mt-1.5 text-2xl font-semibold", TXT[t])}>{value === null || value === undefined ? "n/a" : fmt ? fmt(value) : pct(value)}</p>
      {value !== null && value !== undefined && !fmt && <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-700"><div className={cx("h-full rounded-full", BAR[t])} style={{ width: `${Math.min(100, value * 100)}%` }} /></div>}
      {ci && <p className="mt-1.5 text-[11px] text-slate-500">95% CI {pct(ci[0])} to {pct(ci[1])}</p>}
      {sub && <p className="mt-1 text-[11px] text-slate-500">{sub}</p>}
    </div>
  );
}

export function GroupedBars({ rows, legend }: { rows: { label: string; values: { name: string; v: number | null | undefined; color: string }[] }[]; legend: { name: string; color: string }[] }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-4 text-xs text-slate-400">{legend.map((l) => <span key={l.name} className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: l.color }} />{l.name}</span>)}</div>
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[8rem_1fr] items-start gap-3 text-xs">
          <span className="pt-0.5 font-medium text-slate-300">{r.label}</span>
          <div className="space-y-1">{r.values.map((b) => (
            <div key={b.name} className="flex items-center gap-2"><div className="h-3.5 flex-1 overflow-hidden rounded bg-ink-700"><div className="h-full rounded" style={{ width: `${Math.min(100, (b.v || 0) * 100)}%`, background: b.color }} /></div><span className="w-10 text-right text-slate-300">{pct(b.v)}</span></div>))}</div>
        </div>))}
    </div>
  );
}

export function LineChart({ series, vlines = [] }: { series: { name: string; color: string; points: [number, number][] }[]; vlines?: { x: number; label: string; color: string }[] }) {
  const W = 620, H = 210, L = 38, R = 12, T = 12, B = 30;
  const X = (x: number) => L + x * (W - L - R), Y = (y: number) => T + (1 - y) * (H - T - B);
  return (
    <div>
      <div className="mb-1 flex flex-wrap gap-4 text-xs text-slate-400">{series.map((s) => <span key={s.name} className="flex items-center gap-1.5"><i className="h-0.5 w-4" style={{ background: s.color }} />{s.name}</span>)}</div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Metric versus threshold">
        {[0, 0.25, 0.5, 0.75, 1].map((g) => <g key={g}><line x1={L} x2={W - R} y1={Y(g)} y2={Y(g)} stroke="#22304f" strokeWidth="1" /><text x={L - 6} y={Y(g) + 3} textAnchor="end" fontSize="9" fill="#94a3b8">{Math.round(g * 100)}%</text></g>)}
        {[0, 0.2, 0.4, 0.6, 0.8, 1].map((g) => <text key={g} x={X(g)} y={H - 12} textAnchor="middle" fontSize="9" fill="#94a3b8">{g.toFixed(1)}</text>)}
        <text x={(L + W - R) / 2} y={H - 1} textAnchor="middle" fontSize="9" fill="#94a3b8">evidence threshold (minimum similarity)</text>
        {vlines.map((v) => <g key={v.label}><line x1={X(v.x)} x2={X(v.x)} y1={T} y2={H - B} stroke={v.color} strokeDasharray="4 3" strokeWidth="1.4" /><text x={X(v.x) + 3} y={T + 9} fontSize="9" fill={v.color}>{v.label}</text></g>)}
        {series.map((s) => <polyline key={s.name} fill="none" stroke={s.color} strokeWidth="2" points={s.points.map(([x, y]) => `${X(x)},${Y(y)}`).join(" ")} />)}
      </svg>
    </div>
  );
}
