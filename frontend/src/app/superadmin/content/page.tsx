"use client";
import { useState } from "react";
import { History, Pencil, Plus, Trash2 } from "lucide-react";
import { api, fmtDate } from "@/lib/api";
import { ICON_NAMES } from "@/components/marketing";
import { Markdown } from "@/components/markdown";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Modal, PageHeader, PageLoader, Select, StatusBadge, Table, Tabs, Td, Textarea, useLoad, useToast } from "@/components/ui";

export default function ContentPage() {
  const [tab, setTab] = useState("site");
  return (
    <>
      <PageHeader title="Site & onboarding content" subtitle="Everything visitors and new companies read is stored in the database and edited here. No code changes needed." />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "site", label: "Landing page" }, { id: "steps", label: "Onboarding pages & terms" }, { id: "fields", label: "Request form fields" }]} />
      {tab === "site" ? <SiteTab /> : tab === "steps" ? <StepsTab /> : <FieldsTab />}
    </>
  );
}

/* ---------------- landing page sections ---------------- */
function SiteTab() {
  const toast = useToast();
  const { data, loading, reload } = useLoad<any[]>(() => api("/superadmin/site-content"));
  const [m, setM] = useState<any | null>(null);
  const [err, setErr] = useState("");
  async function save() {
    setErr("");
    try { await api(`/superadmin/site-content/${m.key}`, { method: "PUT", body: { label: m.label, position: m.position, is_active: m.is_active, content: m.content } }); toast("Section saved. The public page is updated."); setM(null); reload(true); }
    catch (e: any) { setErr(e.message); }
  }
  const setItem = (i: number, patch: any) => setM({ ...m, content: { ...m.content, items: m.content.items.map((it: any, n: number) => (n === i ? { ...it, ...patch } : it)) } });
  if (loading) return <PageLoader />;
  return (
    <Card title="Landing page sections" subtitle="Shown on the public home page, in this order."
      action={<Button size="sm" onClick={() => { setErr(""); setM({ key: "", label: "", position: (data?.length || 0) + 1, is_active: true, content: { title: "", subtitle: "", body: "", items: [] }, isNew: true }); }}><Plus className="h-3.5 w-3.5" />Add section</Button>}>
      <Table head={["#", "Section", "Headline", "Items", "Status", ""]}>
        {data?.map((s) => (
          <tr key={s.key}><Td>{s.position}</Td><Td className="font-medium text-white">{s.label}<p className="font-mono text-[11px] text-slate-500">{s.key}</p></Td><Td className="max-w-xs">{s.content.title || "—"}</Td><Td>{s.content.items?.length || 0}</Td>
            <Td><StatusBadge status={s.is_active ? "active" : "inactive"} /></Td>
            <Td><div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => { setErr(""); setM(JSON.parse(JSON.stringify(s))); }}><Pencil className="h-3.5 w-3.5" />Edit</Button>
              <Button variant="ghost" size="sm" onClick={async () => { if (confirm(`Delete section "${s.label}"?`)) { await api(`/superadmin/site-content/${s.key}`, { method: "DELETE" }); reload(true); } }}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button></div></Td></tr>))}
      </Table>
      <p className="mt-3 text-xs text-slate-500">Built-in sections: hero, highlights, features, how_it_works, languages, security, faq, cta. Any other key is shown as an extra section.</p>
      <Modal wide open={!!m} onClose={() => setM(null)} title={m?.isNew ? "New section" : `Edit: ${m?.label}`}>
        {m && <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Key"><Input value={m.key} disabled={!m.isNew} onChange={(e) => setM({ ...m, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") })} placeholder="e.g. testimonials" /></Field>
            <Field label="Admin label"><Input value={m.label} onChange={(e) => setM({ ...m, label: e.target.value })} /></Field>
            <Field label="Order"><Input type="number" value={m.position} onChange={(e) => setM({ ...m, position: Number(e.target.value) })} /></Field>
          </div>
          <Field label="Headline"><Input value={m.content.title} onChange={(e) => setM({ ...m, content: { ...m.content, title: e.target.value } })} /></Field>
          <Field label="Subtitle"><Textarea className="min-h-[64px]" value={m.content.subtitle} onChange={(e) => setM({ ...m, content: { ...m.content, subtitle: e.target.value } })} /></Field>
          <Field label="Body (markdown)"><Textarea value={m.content.body} onChange={(e) => setM({ ...m, content: { ...m.content, body: e.target.value } })} /></Field>
          <div>
            <div className="mb-2 flex items-center justify-between"><span className="text-xs font-medium uppercase tracking-wide text-slate-400">Items (cards / steps / FAQ entries)</span>
              <Button size="sm" variant="secondary" onClick={() => setM({ ...m, content: { ...m.content, items: [...m.content.items, { title: "", text: "", icon: "Sparkles" }] } })}><Plus className="h-3.5 w-3.5" />Add item</Button></div>
            <div className="space-y-3">{m.content.items.map((it: any, i: number) => (
              <div key={i} className="grid gap-2 rounded-lg border border-ink-700 bg-ink-900 p-3 sm:grid-cols-[1fr_1.5fr_9rem_auto]">
                <Input placeholder="Title" value={it.title} onChange={(e) => setItem(i, { title: e.target.value })} />
                <Input placeholder="Text" value={it.text} onChange={(e) => setItem(i, { text: e.target.value })} />
                <Select value={it.icon || ""} onChange={(e) => setItem(i, { icon: e.target.value })}><option value="">No icon</option>{ICON_NAMES.map((n) => <option key={n}>{n}</option>)}</Select>
                <Button variant="ghost" size="sm" onClick={() => setM({ ...m, content: { ...m.content, items: m.content.items.filter((_: any, n: number) => n !== i) } })}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button></div>))}</div>
          </div>
          <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={m.is_active} onChange={(e) => setM({ ...m, is_active: e.target.checked })} />Visible on the public page</label>
          <ErrorText>{err}</ErrorText>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setM(null)}>Cancel</Button><Button onClick={save} disabled={!m.key}>Save section</Button></div>
        </div>}
      </Modal>
    </Card>
  );
}

/* ---------------- onboarding pages (versioned) ---------------- */
function StepsTab() {
  const toast = useToast();
  const { data, loading, reload } = useLoad<any[]>(() => api("/superadmin/onboarding-steps"));
  const [m, setM] = useState<any | null>(null);
  const [vers, setVers] = useState<any[] | null>(null);
  const [preview, setPreview] = useState(false);
  const [err, setErr] = useState("");
  async function save() {
    setErr("");
    try {
      const body = { title: m.title, body_markdown: m.body_markdown, requires_acceptance: m.requires_acceptance, position: m.position, is_active: m.is_active, ...(m.isNew ? { key: m.key } : {}) };
      const r = m.isNew ? await api("/superadmin/onboarding-steps", { body }) : await api(`/superadmin/onboarding-steps/${m.id}`, { method: "PUT", body });
      toast(m.isNew ? "Page created" : `Saved. Current version: v${r.version}`); setM(null); reload(true);
    } catch (e: any) { setErr(e.message); }
  }
  if (loading) return <PageLoader />;
  return (
    <Card title="Walkthrough pages" subtitle="Shown to an approved applicant in this order. Changing the text publishes a new version; every acceptance stays linked to the exact version accepted."
      action={<Button size="sm" onClick={() => { setErr(""); setPreview(false); setM({ isNew: true, key: "", title: "", body_markdown: "", requires_acceptance: false, position: (data?.length || 0) + 1, is_active: true }); }}><Plus className="h-3.5 w-3.5" />Add page</Button>}>
      <Table head={["#", "Page", "Version", "Must accept", "Acceptances", "Status", ""]}>
        {data?.map((s) => (
          <tr key={s.id}><Td>{s.position}</Td><Td className="font-medium text-white">{s.title}<p className="font-mono text-[11px] text-slate-500">{s.key}</p></Td><Td><Badge tone="blue">v{s.version}</Badge></Td>
            <Td>{s.requires_acceptance ? <Badge tone="amber">terms checkbox</Badge> : "—"}</Td><Td>{s.acceptances}</Td><Td><StatusBadge status={s.is_active ? "active" : "inactive"} /></Td>
            <Td><div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={async () => setVers(await api(`/superadmin/onboarding-steps/${s.id}/versions`))}><History className="h-3.5 w-3.5" />History</Button>
              <Button variant="ghost" size="sm" onClick={() => { setErr(""); setPreview(false); setM({ ...s }); }}><Pencil className="h-3.5 w-3.5" />Edit</Button></div></Td></tr>))}
      </Table>
      <p className="mt-3 text-xs text-slate-500">The terms text is a starting draft. Have it reviewed for your legal situation before real customers accept it.</p>
      <Modal wide open={!!m} onClose={() => setM(null)} title={m?.isNew ? "New page" : `Edit: ${m?.title}`}>
        {m && <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            {m.isNew && <Field label="Key"><Input value={m.key} onChange={(e) => setM({ ...m, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") })} placeholder="e.g. data_retention" /></Field>}
            <Field label="Title"><Input value={m.title} onChange={(e) => setM({ ...m, title: e.target.value })} /></Field>
            <Field label="Order"><Input type="number" value={m.position} onChange={(e) => setM({ ...m, position: Number(e.target.value) })} /></Field>
          </div>
          <div className="flex items-center justify-between"><span className="text-xs font-medium uppercase tracking-wide text-slate-400">Content (markdown)</span>
            <button className="text-xs text-brand-400 hover:underline" onClick={() => setPreview(!preview)}>{preview ? "Edit" : "Preview"}</button></div>
          {preview ? <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-ink-700 bg-ink-900 p-4"><Markdown>{m.body_markdown}</Markdown></div>
            : <Textarea className="min-h-[300px] font-mono text-xs" value={m.body_markdown} onChange={(e) => setM({ ...m, body_markdown: e.target.value })} />}
          <div className="flex flex-wrap gap-6 text-sm">
            <label className="flex items-center gap-3"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={m.requires_acceptance} onChange={(e) => setM({ ...m, requires_acceptance: e.target.checked })} />Requires an “I accept” checkbox</label>
            <label className="flex items-center gap-3"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={m.is_active} onChange={(e) => setM({ ...m, is_active: e.target.checked })} />Active</label>
          </div>
          {!m.isNew && <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">Saving changed text creates version {m.version + 1}. Applicants who have not finished onboarding will see (and must accept) the new version. Companies that already accepted keep their record of the old one.</p>}
          <ErrorText>{err}</ErrorText>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setM(null)}>Cancel</Button><Button onClick={save}>{m.isNew ? "Create page" : "Save"}</Button></div>
        </div>}
      </Modal>
      <Modal wide open={!!vers} onClose={() => setVers(null)} title="Version history">
        <div className="space-y-3">{vers?.map((v) => (
          <details key={v.id} className="rounded-lg border border-ink-700 bg-ink-900 px-4 py-3"><summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 text-sm text-white">
            <span>v{v.version} · {v.title}</span><span className="text-xs text-slate-400">{fmtDate(v.created_at)} · {v.created_by || "system"} · {v.acceptances} acceptance(s)</span></summary>
            <div className="mt-3 border-t border-ink-700 pt-3"><Markdown>{v.body_markdown}</Markdown></div></details>))}</div>
      </Modal>
    </Card>
  );
}

/* ---------------- request form fields ---------------- */
const blankField = { key: "", label: "", help_text: "", type: "text", options: [] as string[], required: false, position: 0, is_active: true };
function FieldsTab() {
  const toast = useToast();
  const { data, loading, reload } = useLoad<any[]>(() => api("/superadmin/application-fields"));
  const [m, setM] = useState<any | null>(null);
  const [opts, setOpts] = useState("");
  const [err, setErr] = useState("");
  const open = (f: any) => { setErr(""); setM(f); setOpts((f.options || []).join("\n")); };
  async function save() {
    setErr("");
    const body = { ...m, options: opts.split("\n").map((o) => o.trim()).filter(Boolean), help_text: m.help_text || null };
    try { if (m.id) await api(`/superadmin/application-fields/${m.id}`, { method: "PUT", body }); else await api("/superadmin/application-fields", { body }); toast("Field saved"); setM(null); reload(true); }
    catch (e: any) { setErr(e.message); }
  }
  if (loading) return <PageLoader />;
  return (
    <Card title="Company-request form" subtitle="Applicants fill in these fields. Answers are stored with each request."
      action={<Button size="sm" onClick={() => open({ ...blankField, position: (data?.length || 0) + 1 })}><Plus className="h-3.5 w-3.5" />Add field</Button>}>
      <Table head={["#", "Label", "Type", "Required", "Status", ""]}>
        {data?.map((f) => (
          <tr key={f.id}><Td>{f.position}</Td><Td className="font-medium text-white">{f.label}<p className="font-mono text-[11px] text-slate-500">{f.key}{f.is_system ? " · system" : ""}</p></Td><Td><Badge tone="blue">{f.type}</Badge></Td>
            <Td>{f.required ? "yes" : "no"}</Td><Td><StatusBadge status={f.is_active ? "active" : "inactive"} /></Td>
            <Td><div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => open({ ...f })}><Pencil className="h-3.5 w-3.5" />Edit</Button>
              {!f.is_system && <Button variant="ghost" size="sm" onClick={async () => { if (confirm(`Delete "${f.label}"? Existing answers are kept with their requests.`)) { try { await api(`/superadmin/application-fields/${f.id}`, { method: "DELETE" }); reload(true); } catch (e: any) { toast(e.message, "err"); } } }}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button>}</div></Td></tr>))}
      </Table>
      <Modal open={!!m} onClose={() => setM(null)} title={m?.id ? "Edit field" : "New field"}>
        {m && <div className="space-y-4">
          {!m.id && <Field label="Key" hint="Letters, numbers and underscores. Cannot be changed later."><Input value={m.key} onChange={(e) => setM({ ...m, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") })} /></Field>}
          <Field label="Label (the question)"><Input value={m.label} onChange={(e) => setM({ ...m, label: e.target.value })} /></Field>
          <Field label="Help text"><Input value={m.help_text || ""} onChange={(e) => setM({ ...m, help_text: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Type"><Select value={m.type} disabled={m.is_system} onChange={(e) => setM({ ...m, type: e.target.value })}><option value="text">Short text</option><option value="textarea">Long text</option><option value="number">Number</option><option value="select">Single choice</option><option value="multiselect">Multiple choice</option></Select></Field>
            <Field label="Order"><Input type="number" value={m.position} onChange={(e) => setM({ ...m, position: Number(e.target.value) })} /></Field>
          </div>
          {(m.type === "select" || m.type === "multiselect") && <Field label="Choices (one per line)"><Textarea value={opts} onChange={(e) => setOpts(e.target.value)} /></Field>}
          <div className="flex gap-6 text-sm">
            <label className="flex items-center gap-3"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={m.required} disabled={m.is_system} onChange={(e) => setM({ ...m, required: e.target.checked })} />Required</label>
            <label className="flex items-center gap-3"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={m.is_active} disabled={m.is_system} onChange={(e) => setM({ ...m, is_active: e.target.checked })} />Shown</label>
          </div>
          <ErrorText>{err}</ErrorText>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setM(null)}>Cancel</Button><Button onClick={save} disabled={!m.label || (!m.id && !m.key)}>Save</Button></div>
        </div>}
      </Modal>
    </Card>
  );
}
