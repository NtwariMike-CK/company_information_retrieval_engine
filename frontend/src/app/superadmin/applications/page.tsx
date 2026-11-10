"use client";
import Link from "next/link";
import { useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { Badge, Empty, PageHeader, PageLoader, StatusBadge, Table, Tabs, Td, useLoad } from "@/components/ui";

const TABS = [["", "All"], ["pending", "Pending review"], ["needs_info", "Waiting for applicant"], ["approved", "Approved"], ["onboarded", "Onboarded"], ["rejected", "Rejected"]];

export default function ApplicationsPage() {
  const [status, setStatus] = useState("pending");
  const summary = useLoad<Record<string, number>>(() => api("/superadmin/applications/summary"), [status]);
  const list = useLoad<any[]>(() => api(`/superadmin/applications${status ? `?status=${status}` : ""}`), [status]);
  const count = (k: string) => (k === "" ? Object.values(summary.data || {}).reduce((a, b) => a + b, 0) : summary.data?.[k] || 0);
  return (
    <>
      <PageHeader title="Company requests" subtitle="Review companies asking to join the platform: approve, reject with a comment, or ask for more information." />
      <Tabs value={status} onChange={setStatus} tabs={TABS.map(([id, label]) => ({ id, label: `${label} (${count(id)})` }))} />
      {list.loading ? <PageLoader /> : !list.data?.length ? <Empty>No requests in this view.</Empty> : (
        <Table head={["Company", "Applicant", "Status", "Submitted", "Last activity", ""]}>
          {list.data.map((a) => (
            <tr key={a.id} className="hover:bg-ink-800/50">
              <Td><Link href={`/superadmin/applications/${a.id}`} className="font-medium text-white hover:text-brand-300">{a.company_name}</Link>{a.is_resubmission && <span className="ml-2"><Badge tone="blue">resubmission</Badge></span>}</Td>
              <Td><p>{a.applicant_name}</p><p className="text-xs text-slate-400">{a.applicant_email}</p><p className="text-xs text-slate-500">{a.applicant_phone}</p></Td>
              <Td><StatusBadge status={a.status} /></Td><Td>{fmtDate(a.submitted_at)}</Td><Td>{fmtDate(a.last_activity)}</Td>
              <Td><Link href={`/superadmin/applications/${a.id}`} className="text-sm text-brand-400 hover:underline">Review →</Link></Td>
            </tr>))}
        </Table>)}
    </>
  );
}
