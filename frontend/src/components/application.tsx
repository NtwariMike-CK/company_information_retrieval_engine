"use client";
import { fmtDate } from "@/lib/api";
import { Badge, Field, Input, Select, Textarea, cx } from "./ui";

export type FormField = { key: string; label: string; help_text?: string | null; type: "text" | "textarea" | "number" | "select" | "multiselect"; options: string[]; required: boolean };

/** Renders the company-request form from the field definitions stored in the database. */
export function DynamicForm({ fields, values, onChange, errors = {} }: { fields: FormField[]; values: Record<string, any>; onChange: (v: Record<string, any>) => void; errors?: Record<string, string> }) {
  const set = (k: string, v: any) => onChange({ ...values, [k]: v });
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      {fields.map((f) => {
        const wide = f.type === "textarea" || f.type === "multiselect";
        const label = f.label + (f.required ? " *" : "");
        let control;
        if (f.type === "textarea") control = <Textarea value={values[f.key] || ""} onChange={(e) => set(f.key, e.target.value)} />;
        else if (f.type === "number") control = <Input type="number" min={0} value={values[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value === "" ? "" : Number(e.target.value))} />;
        else if (f.type === "select") control = <Select value={values[f.key] || ""} onChange={(e) => set(f.key, e.target.value)}><option value="">Select…</option>{f.options.map((o) => <option key={o} value={o}>{o}</option>)}</Select>;
        else if (f.type === "multiselect") {
          const cur: string[] = values[f.key] || [];
          control = <div className="flex flex-wrap gap-2">{f.options.map((o) => {
            const on = cur.includes(o);
            return <button type="button" key={o} onClick={() => set(f.key, on ? cur.filter((x) => x !== o) : [...cur, o])}
              className={cx("rounded-lg border px-3 py-1.5 text-sm transition", on ? "border-brand-500 bg-brand-600/25 text-white" : "border-ink-600 text-slate-400 hover:border-slate-400")}>{o}</button>;
          })}</div>;
        } else control = <Input value={values[f.key] || ""} onChange={(e) => set(f.key, e.target.value)} />;
        return (
          <div key={f.key} className={wide ? "sm:col-span-2" : ""}>
            <Field label={label} hint={f.help_text || undefined}>{control}</Field>
            {errors[f.key] && <p className="mt-1 text-xs text-red-300">{errors[f.key]}</p>}
          </div>);
      })}
    </div>
  );
}

const STAGES = [["pending", "Submitted"], ["review", "Under review"], ["approved", "Approved"], ["onboarded", "Workspace ready"]];
export function StatusStepper({ status }: { status: string }) {
  const idx = status === "onboarded" ? 3 : status === "approved" ? 2 : 1;
  const rejected = status === "rejected", info = status === "needs_info";
  return (
    <ol className="flex items-center gap-2">
      {STAGES.map(([k, label], i) => {
        const done = !rejected && i <= idx - (i === idx && status !== "onboarded" ? 1 : 0), current = !rejected && i === idx;
        return (
          <li key={k} className="flex flex-1 items-center gap-2">
            <span className={cx("flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
              rejected && i === 1 ? "bg-red-500/20 text-red-300 ring-1 ring-red-500/40" : done ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40" : current ? "bg-brand-600 text-white shadow-glow" : "bg-ink-700 text-slate-500")}>{i + 1}</span>
            <span className={cx("hidden text-xs sm:block", current ? "font-medium text-white" : "text-slate-500")}>{rejected && i === 1 ? "Not approved" : info && i === 1 ? "More info needed" : label}</span>
            {i < 3 && <span className="h-px flex-1 bg-ink-700" />}
          </li>);
      })}
    </ol>
  );
}

export function Thread({ messages, me }: { messages: any[]; me: "applicant" | "super_admin" }) {
  const label: Record<string, string> = { submission: "Request submitted", info_request: "More information requested", response: "Reply", approval: "Approved", rejection: "Not approved", comment: "Message", status: "Update" };
  return (
    <div className="space-y-3">
      {messages.map((m) => {
        const mine = m.sender_role === me;
        return (
          <div key={m.id} className={cx("flex", mine ? "justify-end" : "justify-start")}>
            <div className={cx("max-w-[88%] rounded-2xl px-4 py-3 text-sm", mine ? "rounded-br-md bg-brand-600/25 ring-1 ring-brand-500/30" : "rounded-bl-md border border-ink-600 bg-ink-850")}>
              <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-slate-400">
                <span>{m.sender_role === "super_admin" ? "Review team" : m.sender_name || "Applicant"}</span><Badge tone={m.kind === "rejection" ? "red" : m.kind === "approval" ? "green" : m.kind === "info_request" ? "amber" : "slate"}>{label[m.kind] || m.kind}</Badge>
              </div>
              <p className="whitespace-pre-wrap text-slate-200">{m.body}</p>
              <p className="mt-1.5 text-[11px] text-slate-500">{fmtDate(m.created_at)}</p>
            </div>
          </div>);
      })}
    </div>
  );
}
