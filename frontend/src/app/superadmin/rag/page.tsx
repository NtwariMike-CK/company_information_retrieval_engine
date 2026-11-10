"use client";
import { useEffect, useState } from "react";
import { KeyRound, Languages, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react";
import { api, fmtDate } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Modal, PageHeader, PageLoader, Select, StatusBadge, Table, Tabs, Td, Textarea, useLoad, useToast } from "@/components/ui";

const TABS = [
  { id: "document_cfg", label: "Documents" }, { id: "cleaning_cfg", label: "Cleaning" }, { id: "chunking_cfg", label: "Chunking" },
  { id: "embedding_cfg", label: "Embedding" }, { id: "retrieval_cfg", label: "Retrieval" }, { id: "llm_cfg", label: "LLM" },
  { id: "prompt_cfg", label: "Prompts" }, { id: "messages_cfg", label: "Messages" }, { id: "chat_cfg", label: "Chat" },
  { id: "languages", label: "Languages" }, { id: "credentials", label: "API credentials" }, { id: "history", label: "History" },
];
const FILE_TYPES = ["pdf", "docx", "txt", "md"];

export default function RagConfigPage() {
  const toast = useToast();
  const cfg = useLoad<any>(() => api("/superadmin/rag-config"));
  const creds = useLoad<any[]>(() => api("/superadmin/credentials"));
  const versions = useLoad<any[]>(() => api("/superadmin/rag-config/versions"));
  const [tab, setTab] = useState("document_cfg");
  const [draft, setDraft] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [liveTest, setLiveTest] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { if (cfg.data) setDraft(JSON.parse(JSON.stringify(cfg.data))); }, [cfg.data]);

  if (cfg.loading || !draft) return <PageLoader />;
  const block = draft[tab] || {};
  const dirty = JSON.stringify(block) !== JSON.stringify(cfg.data[tab]);
  const upd = (patch: any) => setDraft({ ...draft, [tab]: { ...block, ...patch } });
  const num = (k: string) => (e: any) => upd({ [k]: Number(e.target.value) });
  const txt = (k: string) => (e: any) => upd({ [k]: e.target.value });

  async function save() {
    setSaving(true); setError("");
    try {
      const r = await api("/superadmin/rag-config", { method: "PUT", body: { [tab]: block, validate_live: liveTest } });
      toast(r.reprocessing_documents ? `Activated. ${r.reprocessing_documents} document(s) are being re-processed with the new embedding model.` : "Configuration validated and activated globally");
      cfg.reload(true); versions.reload(true);
    } catch (e: any) { setError(e.message); }
    setSaving(false);
  }

  const credSelect = (k: string) => (
    <Field label="API credential" hint="Leave on automatic to use the newest active credential.">
      <Select value={block[k] || ""} onChange={(e) => upd({ [k]: e.target.value || null })}>
        <option value="">Automatic (newest active)</option>
        {creds.data?.filter((c) => c.is_active).map((c) => <option key={c.id} value={c.id}>{c.label} (…{c.key_last4})</option>)}
      </Select>
    </Field>
  );
  const toggle = (k: string, label: string, obj?: string) => {
    const get = obj ? block[obj]?.[k] : block[k];
    return <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={!!get}
      onChange={(e) => (obj ? upd({ [obj]: { ...block[obj], [k]: e.target.checked } }) : upd({ [k]: e.target.checked }))} />{label}</label>;
  };

  const form: Record<string, JSX.Element> = {
    document_cfg: (
      <div className="space-y-4">
        <Field label="Permitted file types">
          <div className="flex flex-wrap gap-4">{FILE_TYPES.map((t) => (
            <label key={t} className="flex items-center gap-2 text-sm uppercase"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={block.allowed_types?.includes(t)}
              onChange={(e) => upd({ allowed_types: e.target.checked ? [...block.allowed_types, t] : block.allowed_types.filter((x: string) => x !== t) })} />{t === "docx" ? "docx (Word)" : t}</label>))}</div>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Max file size (MB)"><Input type="number" min={1} max={200} value={block.max_file_mb} onChange={num("max_file_mb")} /></Field>
          <Field label="Max documents per company"><Input type="number" min={1} value={block.max_files} onChange={num("max_files")} /></Field>
        </div>
      </div>),
    cleaning_cfg: (
      <div className="space-y-3">
        {toggle("normalize_unicode", "Normalize unicode (ligatures, odd characters)")}
        {toggle("fix_hyphenation", "Re-join words hyphenated across lines")}
        {toggle("merge_soft_wraps", "PDF: merge hard-wrapped lines into paragraphs")}
        {toggle("remove_headers_footers", "Remove repeated headers, footers and page numbers")}
        {toggle("collapse_whitespace", "Collapse extra whitespace")}
        {toggle("drop_duplicate_paragraphs", "Drop duplicate paragraphs")}
        <p className="text-xs text-slate-500">EDA statistics (pages, words, empty pages, duplicate ratio, removed lines) are computed for every document and shown to company admins.</p>
      </div>),
    chunking_cfg: (
      <div className="space-y-4">
        <Field label="Strategy"><Select value={block.strategy} onChange={txt("strategy")}>
          <option value="parent_child">Parent–child (search small chunks, answer with the larger parent)</option>
          <option value="recursive">Recursive (paragraph → sentence → word)</option><option value="fixed">Fixed size</option></Select></Field>
        {block.strategy === "parent_child" ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Parent size (characters)"><Input type="number" value={block.parent_size} onChange={num("parent_size")} /></Field>
            <Field label="Child size (characters)"><Input type="number" value={block.child_size} onChange={num("child_size")} /></Field>
          </div>) : <Field label="Chunk size (characters)"><Input type="number" value={block.chunk_size} onChange={num("chunk_size")} /></Field>}
        <Field label="Overlap (characters)"><Input type="number" value={block.overlap} onChange={num("overlap")} /></Field>
        <p className="text-xs text-slate-500">Changes apply to documents processed from now on. Re-upload documents to re-chunk them.</p>
      </div>),
    embedding_cfg: (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Provider"><Select value={block.provider} onChange={txt("provider")}><option value="google">Google (Gemini)</option><option value="fake">Fake (offline testing)</option></Select></Field>
          <Field label="Model identifier"><Input value={block.model} onChange={txt("model")} /></Field>
          <Field label="Dimensions" hint="Fixed at 768 by the database schema."><Input value={block.dimensions} disabled /></Field>
          <Field label="Batch size"><Input type="number" min={1} max={100} value={block.batch_size} onChange={num("batch_size")} /></Field>
        </div>
        {credSelect("credential_id")}
        <p className="text-xs text-amber-300/80">Changing the embedding model automatically re-processes every company's documents (old and new vectors are not comparable). Until a document is re-processed, it is found by keyword search only. Recommended for English + Kinyarwanda: <b>gemini-embedding-2</b>. Run the check in the Languages tab afterwards.</p>
      </div>),
    retrieval_cfg: (
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-3 rounded-lg border border-ink-700 p-4"><p className="text-sm font-medium text-white">Dense (vector search)</p>{toggle("enabled", "Enabled", "dense")}
            <Field label="Top-K"><Input type="number" min={1} value={block.dense?.top_k} onChange={(e) => upd({ dense: { ...block.dense, top_k: Number(e.target.value) } })} /></Field></div>
          <div className="space-y-3 rounded-lg border border-ink-700 p-4"><p className="text-sm font-medium text-white">Sparse (keyword search)</p>{toggle("enabled", "Enabled", "sparse")}
            <Field label="Top-K"><Input type="number" min={1} value={block.sparse?.top_k} onChange={(e) => upd({ sparse: { ...block.sparse, top_k: Number(e.target.value) } })} /></Field></div>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Chunks sent to LLM"><Input type="number" min={1} max={20} value={block.final_k} onChange={num("final_k")} /></Field>
          <Field label="Evidence threshold (0–1)" hint="Min. dense similarity to count as 'information found'."><Input type="number" step="0.05" min={0} max={1} value={block.min_score} onChange={num("min_score")} /></Field>
          <Field label="RRF constant"><Input type="number" min={1} value={block.rrf_k} onChange={num("rrf_k")} /></Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Query transformation"><Select value={block.query_transform || ""} onChange={(e) => upd({ query_transform: e.target.value || null })}><option value="">None</option><option value="followup_concat">Follow-up context (prepend previous question)</option></Select></Field>
          <Field label="Reranker" hint="No rerankers installed yet. Add one in the backend to enable."><Select disabled value=""><option value="">None</option></Select></Field>
        </div>
      </div>),
    llm_cfg: (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Provider"><Select value={block.provider} onChange={txt("provider")}><option value="google">Google (Gemini)</option><option value="fake">Fake (offline testing)</option></Select></Field>
          <Field label="Model identifier" hint="Use the exact model id shown in Google AI Studio."><Input value={block.model} onChange={txt("model")} /></Field>
          <Field label="Temperature"><Input type="number" step="0.1" min={0} max={2} value={block.temperature} onChange={num("temperature")} /></Field>
          <Field label="Max output tokens" hint="Thinking models spend part of this budget on reasoning."><Input type="number" min={64} value={block.max_output_tokens} onChange={num("max_output_tokens")} /></Field>
        </div>
        {credSelect("credential_id")}
      </div>),
    prompt_cfg: (
      <div className="space-y-4">
        <Field label="System prompt" hint="How the assistant answers using retrieved company information."><Textarea className="min-h-[170px] font-mono text-xs" value={block.system_prompt} onChange={txt("system_prompt")} /></Field>
        <Field label="No-evidence prompt" hint="Used when the knowledge base has nothing relevant. The assistant must not invent company information."><Textarea className="min-h-[130px] font-mono text-xs" value={block.no_evidence_prompt} onChange={txt("no_evidence_prompt")} /></Field>
      </div>),
    messages_cfg: (
      <div className="space-y-4">
        <Field label="AI service failure"><Textarea value={block.ai_failure} onChange={txt("ai_failure")} /></Field>
        <Field label="Rate limit exceeded"><Textarea value={block.rate_limit} onChange={txt("rate_limit")} /></Field>
        <Field label="Document-processing failure"><Textarea value={block.processing_failure} onChange={txt("processing_failure")} /></Field>
      </div>),
    chat_cfg: (
      <Field label="Max question–answer exchanges per chat" hint="9 = one question + 8 follow-ups. The database caps this at 9."><Input type="number" min={1} max={9} value={block.max_exchanges} onChange={num("max_exchanges")} /></Field>),
  };

  return (
    <>
      <PageHeader title="RAG Configuration" subtitle="Global settings for every company. Changes are tested before they go live; a failed change never replaces the working configuration."
        action={cfg.data && <Badge tone="blue">Active version {cfg.data.version}</Badge>} />
      <Tabs tabs={TABS} value={tab} onChange={(t) => { setTab(t); setError(""); }} />
      {tab === "languages" ? <LanguagesTab /> : tab === "credentials" ? <Credentials creds={creds} /> : tab === "history" ? <History versions={versions} onChange={() => { cfg.reload(true); versions.reload(true); }} /> : (
        <Card title={TABS.find((t) => t.id === tab)?.label}>
          {form[tab]}
          <div className="mt-6 space-y-3 border-t border-ink-700 pt-4">
            <ErrorText>{error}</ErrorText>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" className="accent-blue-500" checked={liveTest} onChange={(e) => setLiveTest(e.target.checked)} />Run a live test call to the embedding and LLM models before activating</label>
              <div className="flex gap-2">
                <Button variant="ghost" disabled={!dirty} onClick={() => setDraft(JSON.parse(JSON.stringify(cfg.data)))}>Reset</Button>
                <Button onClick={save} loading={saving} disabled={!dirty}>Validate &amp; activate</Button>
              </div>
            </div>
          </div>
        </Card>
      )}
    </>
  );
}

function Credentials({ creds }: { creds: ReturnType<typeof useLoad<any[]>> }) {
  const toast = useToast();
  const [modal, setModal] = useState<any | null>(null);
  const [error, setError] = useState("");
  async function save() {
    setError("");
    try {
      if (modal.id) {
        const body: any = { label: modal.label };
        if (modal.api_key) body.api_key = modal.api_key;
        await api(`/superadmin/credentials/${modal.id}`, { method: "PATCH", body });
      } else await api("/superadmin/credentials", { body: { label: modal.label, api_key: modal.api_key } });
      setModal(null); creds.reload(true); toast("Credential saved");
    } catch (e: any) { setError(e.message); }
  }
  async function toggle(c: any) { try { await api(`/superadmin/credentials/${c.id}`, { method: "PATCH", body: { is_active: !c.is_active } }); creds.reload(true); } catch (e: any) { toast(e.message, "err"); } }
  async function remove(c: any) {
    if (!confirm(`Delete credential "${c.label}"?`)) return;
    try { await api(`/superadmin/credentials/${c.id}`, { method: "DELETE" }); creds.reload(true); } catch (e: any) { toast(e.message, "err"); }
  }
  return (
    <Card title="API credentials" subtitle="Keys are encrypted on the server and can never be viewed again, only replaced."
      action={<Button size="sm" onClick={() => { setError(""); setModal({ label: "", api_key: "" }); }}><Plus className="h-3.5 w-3.5" />Add key</Button>}>
      <p className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">Use a key from a billing-enabled Google project for real company data. On Google's free tier, submitted content may be used to improve Google products and reviewed by people, and Google asks not to send confidential information. Your privacy text should match the tier you use.</p>
      {!creds.data?.length ? <Empty>No API keys yet. Add your Google AI Studio key to enable the assistant.</Empty> : (
        <Table head={["Label", "Provider", "Key", "Status", "Added", ""]}>
          {creds.data.map((c) => (
            <tr key={c.id}>
              <Td className="font-medium text-white">{c.label}</Td><Td>{c.provider}</Td><Td className="font-mono text-xs">••••••••{c.key_last4}</Td>
              <Td><StatusBadge status={c.is_active ? "active" : "inactive"} /></Td><Td>{fmtDate(c.created_at)}</Td>
              <Td><div className="flex justify-end gap-1">
                <Button variant="ghost" size="sm" onClick={() => { setError(""); setModal({ id: c.id, label: c.label, api_key: "" }); }}><KeyRound className="h-3.5 w-3.5" />Edit / replace</Button>
                <Button variant="ghost" size="sm" onClick={() => toggle(c)}>{c.is_active ? "Disable" : "Enable"}</Button>
                <Button variant="ghost" size="sm" onClick={() => remove(c)}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button></div></Td>
            </tr>))}
        </Table>)}
      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.id ? "Edit credential" : "Add API credential"}>
        {modal && <div className="space-y-4">
          <Field label="Label"><Input value={modal.label} onChange={(e) => setModal({ ...modal, label: e.target.value })} placeholder="e.g. Google AI Studio (production)" /></Field>
          <Field label={modal.id ? "New API key (leave empty to keep the current key)" : "API key"}><Input type="password" autoComplete="off" value={modal.api_key} onChange={(e) => setModal({ ...modal, api_key: e.target.value })} /></Field>
          <ErrorText>{error}</ErrorText>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setModal(null)}>Cancel</Button><Button onClick={save}>Save</Button></div>
        </div>}
      </Modal>
    </Card>
  );
}

function History({ versions, onChange }: { versions: ReturnType<typeof useLoad<any[]>>; onChange: () => void }) {
  const toast = useToast();
  async function rollback(id: string) {
    if (!confirm("Roll back to this configuration for all companies?")) return;
    try { await api(`/superadmin/rag-config/${id}/rollback`, { method: "POST" }); toast("Configuration rolled back"); onChange(); } catch (e: any) { toast(e.message, "err"); }
  }
  return (
    <Card title="Configuration history">
      <Table head={["Version", "Status", "Created", "Activated", "Live test", ""]}>
        {versions.data?.map((v) => (
          <tr key={v.id}>
            <Td className="font-medium text-white">v{v.version}</Td><Td><StatusBadge status={v.status} /></Td><Td>{fmtDate(v.created_at)}</Td><Td>{fmtDate(v.activated_at)}</Td>
            <Td className="text-xs text-slate-400">{v.validation_report ? (v.validation_report.ok ? "passed" : "failed") : "—"}</Td>
            <Td>{v.status === "archived" && <Button variant="secondary" size="sm" onClick={() => rollback(v.id)}><RotateCcw className="h-3.5 w-3.5" />Roll back</Button>}</Td>
          </tr>))}
      </Table>
    </Card>
  );
}


function LanguagesTab() {
  const toast = useToast();
  const { data, loading, reload } = useLoad<any[]>(() => api("/superadmin/languages"));
  const [m, setM] = useState<any | null>(null);
  const [words, setWords] = useState("");
  const [err, setErr] = useState("");
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<any | null>(null);
  const open = (l: any) => { setErr(""); setM(l); setWords((l.stopwords || []).join(" ")); };
  async function save() {
    setErr("");
    const body = { ...m, stopwords: words.split(/[\s,]+/).filter(Boolean), sample_text: m.sample_text || null, sample_text_en: m.sample_text_en || null, sample_question: m.sample_question || null };
    try { if (m.isNew) await api("/superadmin/languages", { body }); else await api(`/superadmin/languages/${m.code}`, { method: "PUT", body }); toast("Language saved"); setM(null); reload(true); }
    catch (e: any) { setErr(e.message); }
  }
  async function check() {
    setChecking(true); setResult(null);
    try { setResult(await api("/superadmin/languages/check", { method: "POST" })); } catch (e: any) { toast(e.message, "err"); }
    setChecking(false);
  }
  if (loading) return <PageLoader />;
  return (
    <div className="space-y-6">
      <Card title="Supported languages" subtitle="Add a language as data: detection words, sample sentences, then test it. No code changes."
        action={<Button size="sm" onClick={() => open({ isNew: true, code: "", name: "", native_name: "", is_enabled: true, stopwords: [], sample_text: "", sample_text_en: "", sample_question: "", position: (data?.length || 0) + 1 })}><Plus className="h-3.5 w-3.5" />Add language</Button>}>
        <Table head={["Code", "Language", "Detection words", "Self-check sample", "Status", ""]}>
          {data?.map((l) => (
            <tr key={l.code}><Td className="font-mono">{l.code}</Td><Td className="font-medium text-white">{l.name}<p className="text-xs text-slate-500">{l.native_name}</p></Td><Td>{l.stopwords.length}</Td>
              <Td>{l.sample_text ? <Badge tone="green">configured</Badge> : <span className="text-slate-500">—</span>}</Td><Td><StatusBadge status={l.is_enabled ? "active" : "inactive"} /></Td>
              <Td><div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => open({ ...l })}><Pencil className="h-3.5 w-3.5" />Edit</Button>
                {l.code !== "en" && <Button variant="ghost" size="sm" onClick={async () => { if (confirm(`Delete ${l.name}?`)) { try { await api(`/superadmin/languages/${l.code}`, { method: "DELETE" }); reload(true); } catch (e: any) { toast(e.message, "err"); } } }}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button>}</div></Td></tr>))}
        </Table>
      </Card>
      <Card title="Language check" subtitle="Tests the ACTIVE embedding and LLM models: does a question in one language find a document in the other, and does the assistant answer in the right language?"
        action={<Button onClick={check} loading={checking}><Languages className="h-4 w-4" />Run check</Button>}>
        {!result ? <Empty>Run the check after changing the embedding model, the LLM, or adding a language. It makes a few small API calls.</Empty> : (
          <div className="space-y-5">
            <p className="text-xs text-slate-400">Embedding model: <b className="text-slate-200">{result.embedding_model}</b> · LLM: <b className="text-slate-200">{result.llm_model}</b></p>
            {result.languages.map((r: any) => (
              <div key={r.code} className="rounded-lg border border-ink-700 bg-ink-900 p-4">
                <p className="mb-3 text-sm font-semibold text-white">{r.name} <span className="font-mono text-xs text-slate-500">({r.code})</span></p>
                <div className="grid gap-4 md:grid-cols-2">
                  <div><p className="mb-1.5 text-xs uppercase tracking-wide text-slate-400">Cross-language retrieval {r.embedding?.ok ? <Badge tone="green">passed</Badge> : <Badge tone="red">failed</Badge>}</p>
                    {r.embedding?.error ? <p className="text-xs text-red-300">{r.embedding.error}</p> : (<div className="space-y-1 text-xs text-slate-300">
                      <p>Ask in {r.name}, document in English: match <b>{r.embedding.ask_in_language_doc_in_english.match}</b> vs unrelated {r.embedding.ask_in_language_doc_in_english.unrelated}</p>
                      <p>Ask in English, document in {r.name}: match <b>{r.embedding.ask_in_english_doc_in_language.match}</b> vs unrelated {r.embedding.ask_in_english_doc_in_language.unrelated}</p>
                      <p className="text-slate-400">Suggested evidence threshold (Retrieval → min score): <b className="text-brand-300">{r.embedding.suggested_min_score}</b></p></div>)}</div>
                  <div><p className="mb-1.5 text-xs uppercase tracking-wide text-slate-400">LLM answer in {r.name} {r.llm?.ok ? <Badge tone="green">replied in {r.name}</Badge> : <Badge tone="amber">check manually</Badge>}</p>
                    {r.llm?.error ? <p className="text-xs text-red-300">{r.llm.error}</p> : <><p className="whitespace-pre-wrap rounded-md bg-ink-800 p-3 text-xs text-slate-200">{r.llm.answer}</p><p className="mt-1.5 text-[11px] text-slate-500">{r.llm.note}</p></>}</div>
                </div>
              </div>))}
            {!result.languages.length && <Empty>No enabled language has sample sentences configured.</Empty>}
            <p className="text-xs text-slate-500">{result.note}</p>
          </div>)}
      </Card>
      <Modal wide open={!!m} onClose={() => setM(null)} title={m?.isNew ? "Add language" : `Edit ${m?.name}`}>
        {m && <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Code" hint="2-3 letters (sw, fr…)"><Input value={m.code} disabled={!m.isNew} onChange={(e) => setM({ ...m, code: e.target.value.toLowerCase() })} /></Field>
            <Field label="Name (English)"><Input value={m.name} onChange={(e) => setM({ ...m, name: e.target.value })} /></Field>
            <Field label="Native name"><Input value={m.native_name} onChange={(e) => setM({ ...m, native_name: e.target.value })} /></Field>
          </div>
          <Field label="Detection words" hint="Very common function words of this language, separated by spaces. Words that also exist in another language should be left out."><Textarea className="min-h-[90px] font-mono text-xs" value={words} onChange={(e) => setWords(e.target.value)} /></Field>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Sample sentences for the language check (optional)</p>
          <Field label="A sentence in this language"><Input value={m.sample_text || ""} onChange={(e) => setM({ ...m, sample_text: e.target.value })} /></Field>
          <Field label="Its English translation"><Input value={m.sample_text_en || ""} onChange={(e) => setM({ ...m, sample_text_en: e.target.value })} /></Field>
          <Field label="A question in this language that the English sentence answers"><Input value={m.sample_question || ""} onChange={(e) => setM({ ...m, sample_question: e.target.value })} /></Field>
          <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={m.is_enabled} onChange={(e) => setM({ ...m, is_enabled: e.target.checked })} />Enabled</label>
          <ErrorText>{err}</ErrorText>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setM(null)}>Cancel</Button><Button onClick={save} disabled={!m.name || !m.native_name || (m.isNew && !m.code)}>Save</Button></div>
        </div>}
      </Modal>
    </div>
  );
}
