"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useState } from "react";
import { Menu, LogOut, ArrowLeftCircle, Bot } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { tokenStore } from "@/lib/api";
import { cx } from "./ui";

export type NavItem = { href: string; label: string; icon: ReactNode; badge?: number };

export function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 shadow-glow"><Bot className="h-4.5 w-4.5 text-white" size={18} /></div>
      <div className="leading-tight"><p className="text-sm font-semibold text-white">Company RAG</p><p className="text-[11px] text-slate-400">Knowledge Assistant</p></div>
    </div>
  );
}

export function Shell({ nav, roleLabel, children }: { nav: NavItem[]; roleLabel: string; children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, refresh } = useAuth();
  const [open, setOpen] = useState(false);
  const impersonating = tokenStore.impersonating();
  const active = (href: string) => (href === nav[0].href ? pathname === href : pathname.startsWith(href));

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="px-4 py-5"><Brand /></div>
      <nav className="flex-1 space-y-1 px-3">
        {nav.map((n) => (
          <Link key={n.href} href={n.href} onClick={() => setOpen(false)}
            className={cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
              active(n.href) ? "bg-brand-600/20 text-white ring-1 ring-brand-500/40" : "text-slate-400 hover:bg-ink-800 hover:text-slate-100")}>
            {n.icon}<span className="flex-1">{n.label}</span>{!!n.badge && <span className="rounded-full bg-brand-600 px-2 py-0.5 text-[11px] font-semibold text-white">{n.badge}</span>}
          </Link>
        ))}
      </nav>
      <div className="border-t border-ink-700 p-4">
        <p className="truncate text-sm font-medium text-white">{user?.full_name}</p>
        <p className="truncate text-xs text-slate-400">{user?.email}</p>
        <p className="mt-1 text-[11px] uppercase tracking-wider text-brand-400">{roleLabel}{user?.company_name ? ` · ${user.company_name}` : ""}</p>
        <button onClick={logout} className="mt-3 flex items-center gap-2 text-xs text-slate-400 hover:text-white"><LogOut className="h-3.5 w-3.5" />Sign out</button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:flex">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-ink-700 bg-ink-900 lg:block">{sidebar}</aside>
      {open && <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setOpen(false)}><aside className="h-full w-64 bg-ink-900" onClick={(e) => e.stopPropagation()}>{sidebar}</aside></div>}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3 border-b border-ink-700 bg-ink-900 px-4 py-3 lg:hidden">
          <button onClick={() => setOpen(true)} aria-label="Menu"><Menu className="h-5 w-5 text-slate-300" /></button><Brand />
        </div>
        {impersonating && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-500/30 bg-amber-500/10 px-6 py-2 text-sm text-amber-200">
            <span>You are viewing <b>{impersonating}</b> as its company admin. Actions are audited.</span>
            <button className="flex items-center gap-1.5 font-medium hover:text-white"
              onClick={async () => { tokenStore.stopImpersonation(); await refresh(); router.push("/superadmin"); }}>
              <ArrowLeftCircle className="h-4 w-4" />Return to SuperAdmin</button>
          </div>
        )}
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
