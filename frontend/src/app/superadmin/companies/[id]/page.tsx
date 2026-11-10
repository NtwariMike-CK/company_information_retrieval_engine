"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { api, fmtDate } from "@/lib/api";
import { Card, Empty, ErrorText, PageHeader, PageLoader, Stat, StatusBadge, Table, Td, useLoad } from "@/components/ui";

export default function CompanyDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, loading, error } = useLoad<any>(() => api(`/superadmin/companies/${id}`), [id]);
  if (loading) return <PageLoader />;
  if (error || !data) return <ErrorText>{error || "Not found"}</ErrorText>;
  const { company: c, admins, employees, analytics: a, latest_deletion: del, recent_activity } = data;
  return (
    <>
      <Link href="/superadmin" className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />All companies</Link>
      <PageHeader title={c.name} subtitle={`Registered ${fmtDate(c.created_at)}`}
        action={<div className="flex gap-2"><StatusBadge status={c.access_status} /><StatusBadge status={c.chatbot_state} /><StatusBadge status={c.kb_status} /></div>} />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat label="Employees" value={employees.total} hint={`${employees.active} active`} />
        <Stat label="Questions" value={a.questions} />
        <Stat label="No-evidence answers" value={a.no_evidence} />
        <Stat label="Avg rating" value={a.avg_rating ?? "—"} hint={`${a.rating_count} ratings`} />
        <Stat label="Conversations" value={a.conversations} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Administrators">
          <Table head={["Name", "Email", "Phone", "Last login"]}>
            {admins.map((x: any) => <tr key={x.id}><Td>{x.full_name}</Td><Td>{x.email}</Td><Td>{x.phone || "—"}</Td><Td>{fmtDate(x.last_login_at)}</Td></tr>)}
          </Table>
        </Card>
        <Card title="Documents">
          {a.documents_by_status.length ? <div className="flex flex-wrap gap-3">{a.documents_by_status.map((d: any) => <div key={d.status} className="flex items-center gap-2"><StatusBadge status={d.status} /><span className="text-lg font-semibold text-white">{d.n}</span></div>)}</div> : <Empty>No documents uploaded.</Empty>}
          {del && <p className="mt-4 text-xs text-slate-400">Latest deletion job: <StatusBadge status={del.status} /> · {fmtDate(del.created_at)}</p>}
        </Card>
        <Card title="Recent admin activity" className="lg:col-span-2">
          {recent_activity.length ? <Table head={["Action", "When"]}>{recent_activity.map((r: any, i: number) => <tr key={i}><Td className="font-mono text-xs">{r.action}</Td><Td>{fmtDate(r.created_at)}</Td></tr>)}</Table> : <Empty>No activity yet.</Empty>}
        </Card>
        <Card title="Errors (last 30 days)" className="lg:col-span-2">
          {a.errors_last_30_days.length ? <Table head={["Source", "Code", "Count"]}>{a.errors_last_30_days.map((e: any, i: number) => <tr key={i}><Td>{e.source}</Td><Td className="font-mono text-xs">{e.error_code}</Td><Td>{e.n}</Td></tr>)}</Table> : <Empty>No errors recorded.</Empty>}
        </Card>
      </div>
    </>
  );
}
