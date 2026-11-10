"use client";
import { useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { api, fmtDate } from "@/lib/api";
import { Badge, Button, Empty, ErrorText, Field, Input, Modal, PageHeader, PageLoader, Select, StatusBadge, Table, Td, useLoad, useToast } from "@/components/ui";

const blank = { full_name: "", email: "", password: "", role: "employee", status: "active" };

export default function EmployeesPage() {
  const toast = useToast();
  const { data, loading, reload } = useLoad<any[]>(() => api("/company/employees"));
  const [modal, setModal] = useState<any | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true); setError("");
    try {
      if (modal.id) {
        const body: any = { full_name: modal.full_name, role: modal.role, status: modal.status };
        if (modal.password) body.password = modal.password;
        await api(`/company/employees/${modal.id}`, { method: "PATCH", body });
      } else await api("/company/employees", { body: modal });
      toast(modal.id ? "Employee updated" : "Employee created"); setModal(null); reload(true);
    } catch (e: any) { setError(e.message); }
    setBusy(false);
  }
  const open = (m: any) => { setError(""); setModal(m); };
  return (
    <>
      <PageHeader title="Employees" subtitle="Create accounts for the people in your company who will use the assistant."
        action={<Button onClick={() => open({ ...blank })}><Plus className="h-4 w-4" />Add employee</Button>} />
      {loading ? <PageLoader /> : !data?.length ? <Empty>No employees yet.</Empty> : (
        <Table head={["Name", "Email", "Role", "Status", "Last login", ""]}>
          {data.map((u) => (
            <tr key={u.id} className="hover:bg-ink-800/50">
              <Td className="font-medium text-white">{u.full_name}</Td><Td>{u.email}</Td>
              <Td><Badge tone={u.role === "company_admin" ? "blue" : "slate"}>{u.role.replace("_", " ")}</Badge></Td>
              <Td><StatusBadge status={u.status} /></Td><Td>{fmtDate(u.last_login_at)}</Td>
              <Td><div className="flex justify-end"><Button variant="ghost" size="sm" onClick={() => open({ id: u.id, full_name: u.full_name, role: u.role, status: u.status, password: "" })}><Pencil className="h-3.5 w-3.5" />Edit</Button></div></Td>
            </tr>))}
        </Table>)}
      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.id ? "Edit employee" : "Add employee"}>
        {modal && <div className="space-y-4">
          <Field label="Full name"><Input value={modal.full_name} onChange={(e) => setModal({ ...modal, full_name: e.target.value })} /></Field>
          {!modal.id && <Field label="Email"><Input type="email" value={modal.email} onChange={(e) => setModal({ ...modal, email: e.target.value })} /></Field>}
          <Field label={modal.id ? "Reset password (optional)" : "Password"} hint="At least 8 characters."><Input type="password" autoComplete="new-password" value={modal.password} onChange={(e) => setModal({ ...modal, password: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Role"><Select value={modal.role} onChange={(e) => setModal({ ...modal, role: e.target.value })}><option value="employee">Employee</option><option value="company_admin">Company admin</option></Select></Field>
            <Field label="Status"><Select value={modal.status} onChange={(e) => setModal({ ...modal, status: e.target.value })}><option value="active">Active</option><option value="inactive">Inactive</option></Select></Field>
          </div>
          <ErrorText>{error}</ErrorText>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setModal(null)}>Cancel</Button><Button loading={busy} onClick={save}>{modal.id ? "Save changes" : "Create employee"}</Button></div>
        </div>}
      </Modal>
    </>
  );
}
