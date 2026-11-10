"use client";
import { ReactNode } from "react";
import { Building2, BarChart3, ClipboardCheck, FileInput, FlaskConical, LayoutTemplate, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Shell } from "@/components/shell";
import { PageLoader } from "@/components/ui";
import { useRequireRole } from "@/lib/auth";

const baseNav = [
  { href: "/superadmin", label: "Companies", icon: <Building2 className="h-4 w-4" /> },
  { href: "/superadmin/applications", label: "Company requests", icon: <FileInput className="h-4 w-4" /> },
  { href: "/superadmin/rag", label: "RAG Configuration", icon: <SlidersHorizontal className="h-4 w-4" /> },
  { href: "/superadmin/evaluation", label: "Evaluation", icon: <ClipboardCheck className="h-4 w-4" /> },
  { href: "/superadmin/model-eval", label: "Model evaluation", icon: <FlaskConical className="h-4 w-4" /> },
  { href: "/superadmin/content", label: "Site & onboarding content", icon: <LayoutTemplate className="h-4 w-4" /> },
  { href: "/superadmin/analytics", label: "Analytics & Reports", icon: <BarChart3 className="h-4 w-4" /> },
];

export default function SuperAdminLayout({ children }: { children: ReactNode }) {
  const { user } = useRequireRole("super_admin");
  const [pending, setPending] = useState(0);
  useEffect(() => {
    if (!user) return;
    const load = () => api("/superadmin/applications/summary").then((s: any) => setPending(s.pending || 0)).catch(() => {});
    load(); const t = setInterval(load, 30000); return () => clearInterval(t);
  }, [user]);
  if (!user) return <PageLoader />;
  const nav = baseNav.map((n) => (n.href === "/superadmin/applications" ? { ...n, badge: pending } : n));
  return <Shell nav={nav} roleLabel="SuperAdmin">{children}</Shell>;
}
