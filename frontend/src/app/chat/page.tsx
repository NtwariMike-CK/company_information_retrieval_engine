"use client";
import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { AlertCircle, Bot, FileText, Flag, Loader2, LogOut, Menu, MessageSquarePlus, Send, Star } from "lucide-react";
import { api, fmtDate } from "@/lib/api";
import { useAuth, useRequireRole } from "@/lib/auth";
import { Brand } from "@/components/shell";
import { Badge, Button, cx, ErrorText, Field, PageLoader, Select, StatusBadge, Textarea, useToast } from "@/components/ui";

type Msg = { id?: string; role: "user" | "assistant"; content: string; sources?: { filename: string; page?: number }[]; error?: boolean; has_evidence?: boolean };
type EvalQ = { id: string; text: string; type: "rating_1_5" | "true_false" };

const STAGES = ["Searching company documents…", "Preparing an answer…"];
const REPORT_TYPES = [["incorrect_answer", "Incorrect or incomplete answer"], ["missing_information", "Missing company information"], ["technical_issue", "Technical issue"], ["recommendation", "Recommendation for improvement"], ["other", "Other concern"]];

export default function ChatPage() {
  const { user } = useRequireRole("employee");
  const { logout } = useAuth();
  const toast = useToast();
  const [view, setView] = useState<"chat" | "report">("chat");
  const [convs, setConvs] = useState<any[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [status, setStatus] = useState<{ available: boolean; chatbot_state: string; max_exchanges: number } | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [stage, setStage] = useState(0);
  const [evalFor, setEvalFor] = useState<{ messageId: string; questions: EvalQ[] } | null>(null);
  const [sidebar, setSidebar] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const loadConvs = () => api<any[]>("/chat/conversations").then(setConvs).catch(() => {});
  useEffect(() => { if (user) { loadConvs(); api("/chat/status").then(setStatus).catch(() => {}); } }, [user]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, sending, evalFor]);
  useEffect(() => { if (!sending) return; setStage(0); const t = setTimeout(() => setStage(1), 1800); return () => clearTimeout(t); }, [sending]);

  const newChat = () => { setActiveId(null); setMsgs([]); setEvalFor(null); setRemaining(null); setView("chat"); setSidebar(false); };
  async function openChat(id: string) {
    try {
      const c = await api(`/chat/conversations/${id}`);
      setActiveId(id); setEvalFor(null); setView("chat"); setSidebar(false);
      setMsgs(c.messages.map((m: any) => ({ id: m.id, role: m.role, content: m.content, has_evidence: m.has_evidence })));
      setRemaining(c.remaining_exchanges);
    } catch (e: any) { toast(e.message, "err"); }
  }

  async function send(e?: FormEvent) {
    e?.preventDefault();
    const q = input.trim();
    if (!q || sending) return;
    setSending(true); setEvalFor(null); setInput("");
    setMsgs((m) => [...m, { role: "user", content: q }]);
    try {
      let id = activeId;
      if (!id) { id = (await api("/chat/conversations", { method: "POST" })).id; setActiveId(id); }
      const r = await api(`/chat/conversations/${id}/messages`, { body: { question: q } });
      setMsgs((m) => [...m, { id: r.message_id, role: "assistant", content: r.answer, sources: r.sources, has_evidence: r.has_evidence }]);
      setRemaining(r.remaining_exchanges);
      if (r.evaluation.requested) setEvalFor({ messageId: r.message_id, questions: r.evaluation.questions });
      loadConvs();
    } catch (err: any) {
      if (err.code === "service_unavailable") api("/chat/status").then(setStatus).catch(() => {});
      if (err.code === "chat_limit_reached") setRemaining(0);
      setMsgs((m) => [...m, { role: "assistant", content: err.message, error: true }]);
    }
    setSending(false);
  }
  const onKey = (e: KeyboardEvent) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };

  if (!user) return <PageLoader />;
  const limitReached = remaining === 0;
  const unavailable = status && !status.available;
  const disabled = sending || limitReached || !!unavailable;

  const side = (
    <div className="flex h-full flex-col bg-ink-900">
      <div className="px-4 py-5"><Brand /></div>
      <div className="space-y-1 px-3">
        <button onClick={newChat} className="flex w-full items-center gap-2 rounded-lg border border-ink-600 px-3 py-2 text-sm font-medium text-white hover:bg-ink-800"><MessageSquarePlus className="h-4 w-4" />New chat</button>
        <button onClick={() => { setView("report"); setSidebar(false); }} className={cx("flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm", view === "report" ? "bg-brand-600/20 text-white ring-1 ring-brand-500/40" : "text-slate-400 hover:bg-ink-800 hover:text-white")}><Flag className="h-4 w-4" />Report</button>
      </div>
      <p className="mt-5 px-4 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Chat history</p>
      <div className="mt-2 flex-1 space-y-0.5 overflow-y-auto px-3">
        {convs.length === 0 && <p className="px-3 py-2 text-xs text-slate-500">No chats yet.</p>}
        {convs.map((c) => (
          <button key={c.id} onClick={() => openChat(c.id)} className={cx("w-full truncate rounded-lg px-3 py-2 text-left text-sm transition", activeId === c.id && view === "chat" ? "bg-ink-700 text-white" : "text-slate-400 hover:bg-ink-800 hover:text-slate-100")} title={c.title || "New chat"}>{c.title || "New chat"}</button>))}
      </div>
      <div className="border-t border-ink-700 p-4">
        <p className="truncate text-sm font-medium text-white">{user.full_name}</p><p className="truncate text-xs text-slate-400">{user.company_name}</p>
        <button onClick={logout} className="mt-3 flex items-center gap-2 text-xs text-slate-400 hover:text-white"><LogOut className="h-3.5 w-3.5" />Sign out</button>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen">
      <aside className="hidden w-72 shrink-0 border-r border-ink-700 lg:block">{side}</aside>
      {sidebar && <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setSidebar(false)}><aside className="h-full w-72" onClick={(e) => e.stopPropagation()}>{side}</aside></div>}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-ink-700 bg-ink-900 px-4 py-3 lg:hidden"><button onClick={() => setSidebar(true)} aria-label="Menu"><Menu className="h-5 w-5 text-slate-300" /></button><span className="text-sm font-medium text-white">{view === "report" ? "Report" : "Assistant"}</span></div>

        {view === "report" ? <ReportView onDone={() => setView("chat")} activeId={activeId} /> : (
          <>
            <div className="flex-1 overflow-y-auto">
              <div className="mx-auto max-w-3xl px-4 py-8">
                {msgs.length === 0 && !sending && (
                  <div className="flex min-h-[50vh] flex-col items-center justify-center text-center">
                    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 shadow-glow"><Bot className="h-7 w-7 text-white" /></div>
                    <h1 className="text-2xl font-semibold text-white">How can I help, {user.full_name.split(" ")[0]}?</h1>
                    <p className="mt-2 max-w-md text-sm text-slate-400">Ask a question about {user.company_name || "your company"}. Answers come from your company's own documents.</p>
                    {unavailable && <div className="mt-6"><Badge tone="amber">{status?.chatbot_state === "paused" ? "The assistant is paused by your administrator" : "The assistant isn't available yet"}</Badge></div>}
                  </div>)}
                <div className="space-y-6">
                  {msgs.map((m, i) => m.role === "user" ? (
                    <div key={i} className="flex justify-end"><div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-sm text-white">{m.content}</div></div>
                  ) : (
                    <div key={i} className="flex gap-3">
                      <div className={cx("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", m.error ? "bg-red-500/20" : "bg-ink-700")}>{m.error ? <AlertCircle className="h-4 w-4 text-red-300" /> : <Bot className="h-4 w-4 text-brand-300" />}</div>
                      <div className="min-w-0 flex-1">
                        {m.error ? <p className="text-sm text-red-300">{m.content}</p> : <div className="chat-md text-slate-200"><ReactMarkdown>{m.content}</ReactMarkdown></div>}
                        {m.sources && m.sources.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">{Array.from(new Map(m.sources.map((s) => [`${s.filename}-${s.page}`, s])).values()).map((s, j) => (
                            <span key={j} className="inline-flex items-center gap-1.5 rounded-md border border-ink-600 bg-ink-850 px-2 py-1 text-xs text-slate-300"><FileText className="h-3 w-3 text-brand-400" />{s.filename}{s.page ? ` · p.${s.page}` : ""}</span>))}</div>)}
                        {evalFor && m.id === evalFor.messageId && <EvalCard key={evalFor.messageId} messageId={evalFor.messageId} questions={evalFor.questions} onDone={() => setEvalFor(null)} />}
                      </div>
                    </div>))}
                  {sending && (
                    <div className="flex gap-3"><div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink-700"><Loader2 className="h-4 w-4 animate-spin text-brand-300" /></div>
                      <div className="flex items-center gap-2 pt-1.5 text-sm text-slate-400"><span>{STAGES[stage]}</span><span className="flex gap-0.5"><i className="dot h-1 w-1 rounded-full bg-slate-400" /><i className="dot h-1 w-1 rounded-full bg-slate-400" /><i className="dot h-1 w-1 rounded-full bg-slate-400" /></span></div></div>)}
                </div>
                <div ref={bottom} />
              </div>
            </div>
            <div className="border-t border-ink-700 bg-ink-950/80 px-4 py-4 backdrop-blur">
              <div className="mx-auto max-w-3xl">
                {limitReached && <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200"><span>This chat reached its limit of {status?.max_exchanges ?? 9} questions.</span><Button size="sm" onClick={newChat}>Start a new chat</Button></div>}
                <form onSubmit={send} className="flex items-end gap-2 rounded-2xl border border-ink-600 bg-ink-850 p-2 focus-within:border-brand-500">
                  <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKey} rows={1} disabled={disabled} maxLength={2000}
                    placeholder={unavailable ? "The assistant is currently unavailable" : limitReached ? "Start a new chat to continue" : "Ask about your company's documents…"}
                    className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none disabled:opacity-60" />
                  <button type="submit" disabled={disabled || !input.trim()} className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-500 disabled:opacity-40" aria-label="Send"><Send className="h-4 w-4" /></button>
                </form>
                <p className="mt-2 text-center text-[11px] text-slate-500">{remaining !== null && !limitReached ? `${remaining} question${remaining === 1 ? "" : "s"} left in this chat · ` : ""}Answers are generated from company documents and may contain mistakes.</p>
              </div>
            </div>
          </>)}
      </div>
    </div>
  );
}

function EvalCard({ messageId, questions, onDone }: { messageId: string; questions: EvalQ[]; onDone: () => void }) {
  const toast = useToast();
  const [ans, setAns] = useState<Record<string, number | boolean>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const complete = questions.every((q) => ans[q.id] !== undefined);

  async function submit() {
    setBusy(true);
    try {
      await api(`/chat/messages/${messageId}/feedback`, { body: { answers: questions.map((q) => ({ question_id: q.id, ...(q.type === "rating_1_5" ? { rating: ans[q.id] } : { bool_value: ans[q.id] }) })) } });
      setDone(true); setTimeout(onDone, 1800);
    } catch (e: any) { toast(e.message, "err"); }
    setBusy(false);
  }
  if (done) return <p className="mt-4 text-sm text-emerald-300">Thanks for your feedback!</p>;
  return (
    <div className="mt-4 rounded-xl border border-ink-600 bg-ink-850 p-4">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Help us improve</p>
      <div className="space-y-4">{questions.map((q) => (
        <div key={q.id}><p className="mb-2 text-sm text-slate-200">{q.text}</p>
          {q.type === "rating_1_5" ? (
            <div className="flex gap-1.5">{[1, 2, 3, 4, 5].map((n) => (
              <button key={n} onClick={() => setAns({ ...ans, [q.id]: n })} aria-label={`${n} star${n > 1 ? "s" : ""}`}
                className={cx("flex h-9 w-9 items-center justify-center rounded-lg border text-sm transition", (ans[q.id] as number) >= n ? "border-brand-500 bg-brand-600/30 text-brand-300" : "border-ink-600 text-slate-500 hover:border-slate-400")}><Star className={cx("h-4 w-4", (ans[q.id] as number) >= n && "fill-current")} /></button>))}</div>
          ) : (
            <div className="flex gap-2">{[true, false].map((v) => (
              <button key={String(v)} onClick={() => setAns({ ...ans, [q.id]: v })} className={cx("rounded-lg border px-4 py-1.5 text-sm transition", ans[q.id] === v ? "border-brand-500 bg-brand-600/30 text-white" : "border-ink-600 text-slate-400 hover:border-slate-400")}>{v ? "True" : "False"}</button>))}</div>)}
        </div>))}</div>
      <div className="mt-4 flex gap-2"><Button size="sm" onClick={submit} loading={busy} disabled={!complete}>Submit</Button><Button size="sm" variant="ghost" onClick={onDone}>Skip</Button></div>
    </div>
  );
}

function ReportView({ onDone, activeId }: { onDone: () => void; activeId: string | null }) {
  const toast = useToast();
  const [type, setType] = useState("incorrect_answer");
  const [comments, setComments] = useState("");
  const [attach, setAttach] = useState(!!activeId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mine, setMine] = useState<any[]>([]);
  const load = () => api<any[]>("/chat/reports").then(setMine).catch(() => {});
  useEffect(() => { load(); }, []);

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      await api("/chat/reports", { body: { type, comments, ...(attach && activeId ? { conversation_id: activeId } : {}) } });
      toast("Report submitted. Thank you!"); setComments(""); load();
    } catch (err: any) { setError(err.message); }
    setBusy(false);
  }
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-4 py-8">
        <h1 className="text-2xl font-semibold text-white">Report</h1>
        <p className="mt-1 text-sm text-slate-400">Tell us about a problem or suggest an improvement.</p>
        <form onSubmit={submit} className="mt-6 space-y-4 rounded-xl border border-ink-700 bg-ink-850 p-5">
          <Field label="Type"><Select value={type} onChange={(e) => setType(e.target.value)}>{REPORT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
          <Field label="Comments"><Textarea required minLength={3} maxLength={4000} value={comments} onChange={(e) => setComments(e.target.value)} placeholder="Describe what happened or what you'd like to see…" /></Field>
          {activeId && <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" className="accent-blue-500" checked={attach} onChange={(e) => setAttach(e.target.checked)} />Attach the chat I currently have open</label>}
          <ErrorText>{error}</ErrorText>
          <div className="flex gap-2"><Button type="submit" loading={busy}>Submit report</Button><Button type="button" variant="ghost" onClick={onDone}>Back to chat</Button></div>
        </form>
        {mine.length > 0 && (
          <div className="mt-8"><h2 className="mb-3 text-sm font-semibold text-white">Your previous reports</h2>
            <div className="space-y-2">{mine.map((r) => (
              <div key={r.id} className="rounded-lg border border-ink-700 bg-ink-850 p-3 text-sm"><div className="mb-1 flex items-center justify-between"><Badge tone="blue">{r.type.replace(/_/g, " ")}</Badge><StatusBadge status={r.status} /></div><p className="text-slate-300">{r.comments}</p><p className="mt-1 text-xs text-slate-500">{fmtDate(r.created_at)}</p></div>))}</div></div>)}
      </div>
    </div>
  );
}
