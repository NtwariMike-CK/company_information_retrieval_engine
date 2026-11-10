"use client";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, tokenStore } from "./api";

export type User = {
  id: string; full_name: string; email: string; role: "super_admin" | "company_admin" | "employee" | "applicant";
  company_id: string | null; company_name: string | null; impersonator?: string | null;
};
const Ctx = createContext<{ user: User | null; loading: boolean; refresh: () => Promise<void>; logout: () => void }>(
  { user: null, loading: true, refresh: async () => {}, logout: () => {} });

export const homeFor = (role: User["role"]) => (role === "super_admin" ? "/superadmin" : role === "company_admin" ? "/admin" : role === "applicant" ? "/apply" : "/chat");

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refresh = async () => {
    if (!tokenStore.get()) { setUser(null); setLoading(false); return; }
    try { setUser(await api<User>("/auth/me")); } catch { setUser(null); }
    setLoading(false);
  };
  useEffect(() => { refresh(); }, []);
  const logout = () => { tokenStore.clear(); setUser(null); router.push("/login"); };
  return <Ctx.Provider value={{ user, loading, refresh, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);

/** Redirects to /login if signed out, or to the user's home if the role does not match. */
export function useRequireRole(role: User["role"]) {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
    else if (user.role !== role) router.replace(homeFor(user.role));
  }, [user, loading, role, router]);
  return { user: user && user.role === role ? user : null, loading };
}
