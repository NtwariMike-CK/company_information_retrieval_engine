"use client";
import { ReactNode } from "react";
import { ClipboardList, ShieldCheck } from "lucide-react";
import { Shell } from "@/components/shell";
import { PageLoader } from "@/components/ui";
import { useRequireRole } from "@/lib/auth";

const nav = [
  { href: "/apply", label: "My request", icon: <ClipboardList className="h-4 w-4" /> },
  { href: "/apply/onboarding", label: "Onboarding", icon: <ShieldCheck className="h-4 w-4" /> },
];

export default function ApplyLayout({ children }: { children: ReactNode }) {
  const { user } = useRequireRole("applicant");
  if (!user) return <PageLoader />;
  return <Shell nav={nav} roleLabel="Applicant">{children}</Shell>;
}
