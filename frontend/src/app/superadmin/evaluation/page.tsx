"use client";
import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Modal, PageHeader, PageLoader, Select, Table, Td, useLoad, useToast } from "@/components/ui";

const blankQ = { text: "", type: "rating_1_5", position: 0, is_active: true };

export default function EvaluationPage() {
  const toast = useToast();
  const settings = useLoad<any>(() => api("/superadmin/evaluation/settings"));
  const questions = useLoad<any[]>(() => api("/superadmin/evaluation/questions"));
  const [s, setS] = useState({ every_n_answers: 1, enabled: true });
  const [editing, setEditing] = useState<any | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (settings.data) setS({ every_n_answers: settings.data.every_n_answers, enabled: settings.data.enabled }); }, [settings.data]);

  async function saveSettings() {
    try { await api("/superadmin/evaluation/settings", { method: "PUT", body: s }); toast("Evaluation settings saved"); } catch (e: any) { toast(e.message, "err"); }
  }
  async function saveQuestion() {
    setError("");
    try {
      if (editing.id) await api(`/superadmin/evaluation/questions/${editing.id}`, { method: "PUT", body: editing });
      else await api("/superadmin/evaluation/questions", { body: editing });
      setEditing(null); questions.reload(true); toast("Question saved");
    } catch (e: any) { setError(e.message); }
  }
  async function remove(q: any) {
    if (!confirm("Delete this question and all answers collected for it?")) return;
    try { await api(`/superadmin/evaluation/questions/${q.id}`, { method: "DELETE" }); questions.reload(true); } catch (e: any) { toast(e.message, "err"); }
  }
  if (settings.loading || questions.loading) return <PageLoader />;

  return (
    <>
      <PageHeader title="Evaluation" subtitle="Control when employees are asked for feedback and what they are asked." />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="When to ask" className="h-fit">
          <div className="space-y-4">
            <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={s.enabled} onChange={(e) => setS({ ...s, enabled: e.target.checked })} />Request feedback from employees</label>
            <Field label="Ask after every N-th answer" hint="1 = after every answer, 2 = after every second answer…">
              <Input type="number" min={1} max={9} value={s.every_n_answers} onChange={(e) => setS({ ...s, every_n_answers: Number(e.target.value) })} />
            </Field>
            <Button onClick={saveSettings}>Save settings</Button>
          </div>
        </Card>
        <Card title="Evaluation questions" subtitle="Rating (1–5) or True/False" className="lg:col-span-2"
          action={<Button size="sm" onClick={() => { setError(""); setEditing({ ...blankQ, position: (questions.data?.length || 0) + 1 }); }}><Plus className="h-3.5 w-3.5" />Add question</Button>}>
          {!questions.data?.length ? <Empty>No questions. Employees will not be asked for feedback.</Empty> : (
            <Table head={["#", "Question", "Type", "Status", ""]}>
              {questions.data.map((q) => (
                <tr key={q.id}>
                  <Td>{q.position}</Td><Td className="max-w-md">{q.text}</Td>
                  <Td><Badge tone="blue">{q.type === "rating_1_5" ? "Rating 1–5" : "True / False"}</Badge></Td>
                  <Td><Badge tone={q.is_active ? "green" : "slate"}>{q.is_active ? "active" : "hidden"}</Badge></Td>
                  <Td><div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => { setError(""); setEditing(q); }}><Pencil className="h-3.5 w-3.5" /></Button><Button variant="ghost" size="sm" onClick={() => remove(q)}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button></div></Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing?.id ? "Edit question" : "New question"}>
        {editing && (
          <div className="space-y-4">
            <Field label="Question text"><Input value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Type"><Select value={editing.type} onChange={(e) => setEditing({ ...editing, type: e.target.value })}><option value="rating_1_5">Rating 1–5</option><option value="true_false">True / False</option></Select></Field>
              <Field label="Order"><Input type="number" value={editing.position} onChange={(e) => setEditing({ ...editing, position: Number(e.target.value) })} /></Field>
            </div>
            <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="h-4 w-4 accent-blue-500" checked={editing.is_active} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} />Active</label>
            <ErrorText>{error}</ErrorText>
            <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button><Button onClick={saveQuestion}>Save</Button></div>
          </div>
        )}
      </Modal>
    </>
  );
}
