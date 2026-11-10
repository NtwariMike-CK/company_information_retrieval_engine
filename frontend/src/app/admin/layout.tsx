"use client";
import { ReactNode } from "react";
import { BarChart3, ClipboardList, FileText, LayoutDashboard, Users } from "lucide-react";
import { Shell } from "@/components/shell";
import { PageLoader } from "@/components/ui";
import { useRequireRole } from "@/lib/auth";

const nav = [
  { href: "/admin", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
  { href: "/admin/documents", label: "Knowledge base", icon: <FileText className="h-4 w-4" /> },
  { href: "/admin/employees", label: "Employees", icon: <Users className="h-4 w-4" /> },
  { href: "/admin/analytics", label: "Analytics", icon: <BarChart3 className="h-4 w-4" /> },
  { href: "/admin/request", label: "Company request", icon: <ClipboardList className="h-4 w-4" /> },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const { user } = useRequireRole("company_admin");
  if (!user) return <PageLoader />;
  return <Shell nav={nav} roleLabel="Company Admin">{children}</Shell>;
}
