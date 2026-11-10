"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, LogIn, Plus, Power } from "lucide-react";
import { api, tokenStore } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Empty, ErrorText, Field, Input, Modal, PageHeader, PageLoader, StatusBadge, Table, Td, useLoad, useToast } from "@/components/ui";

const blank = { company_name: "", admin_name: "", phone: "", email: "", password: "" };

export default function CompaniesPage() {
  const toast = useToast();
  const router = useRouter();
  const { refresh } = useAuth();
  const { data, loading, reload } = useLoad<any[]>(() => api("/superadmin/companies"));
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof blank) => (e: any) => setForm({ ...form, [k]: e.target.value });

  async function create(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      await api("/superadmin/companies", { body: form });
      toast("Company and administrator created");
      setOpen(false); setForm(blank); reload(true);
    } catch (err: any) { setError(err.message); }
    setBusy(false);
  }
  async function toggle(c: any) {
    const next = c.access_status !== "active";
    if (!next && !confirm(`Deactivate ${c.name}? Its admin and employees will no longer be able to use the service.`)) return;
    try { await api(`/superadmin/companies/${c.id}/access`, { method: "PATCH", body: { active: next } }); toast(`${c.name} ${next ? "activated" : "deactivated"}`); reload(true); }
    catch (e: any) { toast(e.message, "err"); }
  }
  async function enter(c: any) {
    try {
      const r = await api(`/superadmin/companies/${c.id}/impersonate`, { method: "POST" });
      tokenStore.startImpersonation(r.access_token, c.name);
      await refresh();
      router.push("/admin");
    } catch (e: any) { toast(e.message, "err"); }
  }

  return (
    <>
      <PageHeader title="Companies" subtitle="Register companies and manage their administrators and access."
        action={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add company</Button>} />
      {loading ? <PageLoader /> : !data?.length ? <Empty>No companies yet. Add the first company to get started.</Empty> : (
        <Table head={["Company", "Administrator", "Employees", "Docs", "Knowledge base", "Chatbot", "Access", ""]}>
          {data.map((c) => (
            <tr key={c.id} className="hover:bg-ink-800/50">
              <Td><Link href={`/superadmin/companies/${c.id}`} className="font-medium text-white hover:text-brand-300">{c.name}</Link></Td>
              <Td><p>{c.admin_name}</p><p className="text-xs text-slate-400">{c.admin_email}</p><p className="text-xs text-slate-500">{c.admin_phone}</p></Td>
              <Td>{c.employees}</Td><Td>{c.documents}</Td>
              <Td><StatusBadge status={c.kb_status} /></Td><Td><StatusBadge status={c.chatbot_state} /></Td>
              <Td><StatusBadge status={c.access_status} /></Td>
              <Td>
                <div className="flex justify-end gap-1.5">
                  <Link href={`/superadmin/companies/${c.id}`}><Button variant="ghost" size="sm" title="View details"><Eye className="h-3.5 w-3.5" /></Button></Link>
                  <Button variant="secondary" size="sm" onClick={() => enter(c)} title="Enter as company admin"><LogIn className="h-3.5 w-3.5" />Enter</Button>
                  <Button variant={c.access_status === "active" ? "danger" : "primary"} size="sm" onClick={() => toggle(c)}><Power className="h-3.5 w-3.5" />{c.access_status === "active" ? "Deactivate" : "Activate"}</Button>
                </div>
              </Td>
            </tr>
          ))}
        </Table>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="Register a company">
        <form onSubmit={create} className="space-y-4">
          <Field label="Company name"><Input required value={form.company_name} onChange={set("company_name")} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Admin name"><Input required value={form.admin_name} onChange={set("admin_name")} /></Field>
            <Field label="Phone"><Input required value={form.phone} onChange={set("phone")} placeholder="+250…" /></Field>
          </div>
          <Field label="Admin email"><Input required type="email" value={form.email} onChange={set("email")} /></Field>
          <Field label="Initial password" hint="At least 8 characters. Share it securely with the admin."><Input required type="password" minLength={8} value={form.password} onChange={set("password")} autoComplete="new-password" /></Field>
          <ErrorText>{error}</ErrorText>
          <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" loading={busy}>Create company</Button></div>
        </form>
      </Modal>
    </>
  );
}
