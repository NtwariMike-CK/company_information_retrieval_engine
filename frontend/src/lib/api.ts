export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, string>;
  constructor(status: number, code: string, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

const TOKEN_KEY = "rag_token";
const SA_TOKEN_KEY = "rag_sa_token";
const SA_CONTEXT_KEY = "rag_impersonating";

export const tokenStore = {
  get: () => (typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY)),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(SA_TOKEN_KEY);
    sessionStorage.removeItem(SA_CONTEXT_KEY);
  },
  // SuperAdmin "enter as admin": keep the SuperAdmin token so they can return
  startImpersonation: (adminToken: string, companyName: string) => {
    sessionStorage.setItem(SA_TOKEN_KEY, localStorage.getItem(TOKEN_KEY) || "");
    sessionStorage.setItem(SA_CONTEXT_KEY, companyName);
    localStorage.setItem(TOKEN_KEY, adminToken);
  },
  impersonating: () => (typeof window === "undefined" ? null : sessionStorage.getItem(SA_CONTEXT_KEY)),
  stopImpersonation: () => {
    const t = sessionStorage.getItem(SA_TOKEN_KEY);
    if (t) localStorage.setItem(TOKEN_KEY, t);
    sessionStorage.removeItem(SA_TOKEN_KEY);
    sessionStorage.removeItem(SA_CONTEXT_KEY);
  },
};

async function request(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the server. Please check your connection and try again.");
  }
  if (!res.ok) {
    let code = "error", message = "Something went wrong. Please try again.";
    let fields: Record<string, string> = {};
    try {
      const j = await res.json();
      if (j?.detail?.code) { code = j.detail.code; message = j.detail.message; fields = j.detail.fields || {}; }
      else if (Array.isArray(j?.detail)) { code = "validation"; message = j.detail.map((d: any) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; "); }
    } catch {}
    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
      tokenStore.clear();
      window.location.href = "/login";
    }
    throw new ApiError(res.status, code, message, fields);
  }
  return res;
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any; form?: FormData } = {}): Promise<T> {
  const init: RequestInit = { method: opts.method || (opts.body || opts.form ? "POST" : "GET") };
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.body);
  }
  const res = await request(path, init);
  return res.json();
}

/** Authenticated file download (CSV / JSON exports). */
export async function download(path: string, filename: string, body?: any) {
  const init: RequestInit = body !== undefined
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const res = await request(path, init);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export const fmtDate = (s?: string | null) =>
  s ? new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";
