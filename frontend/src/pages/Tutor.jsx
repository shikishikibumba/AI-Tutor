import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, streamTutor, errMsg } from "@/lib/api";
import { useModule } from "@/context/ModuleContext";
import { PageHeader } from "@/components/Bits";
import { SourceButton } from "@/components/SourceDrawer";
import { QuestionCard } from "@/components/QuestionCard";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Send, Trash2, ShieldAlert, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const MODES = [
  { id: "explain", label: "Explain" }, { id: "simplify", label: "Simplify" }, { id: "formula", label: "Show Formula" },
  { id: "example", label: "Worked Example" }, { id: "testme", label: "Test Me" }, { id: "mistake", label: "Explain My Mistake" },
];

function Message({ m }) {
  if (m.role === "user") return <div className="flex justify-end"><div className="max-w-[80%] bg-cyan-500/10 border border-cyan-500/30 rounded-md px-4 py-2.5 text-sm">{m.content}</div></div>;
  if (m.question) return <QuestionCard q={m.question} mode="tutor" />;
  return (
    <div data-testid="tutor-message" className="panel p-5">
      <div className="prose-tutor text-sm text-slate-200"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content || "…"}</ReactMarkdown></div>
      {m.done !== false && (
        <div className="mt-3 pt-3 border-t border-slate-800 flex flex-wrap items-center gap-2">
          {m.sources?.length ? m.sources.map((s, i) => <SourceButton key={i} source={s} testId={`tutor-source-${i}`} label={`SOURCE p.${s.page}`} />)
            : !m.insufficient && <span className="flex items-center gap-1.5 text-[11px] text-amber-300 font-mono"><ShieldAlert size={12} /> Source not identified confidently — not presented as source-derived</span>}
          {m.insufficient && <span data-testid="tutor-insufficient" className="text-[11px] font-mono text-amber-300">SOURCE INSUFFICIENT</span>}
          {m.source_flags?.length > 0 && <span className="flex items-center gap-1 text-[11px] text-amber-300"><AlertTriangle size={12} /> Source flagged for review</span>}
        </div>
      )}
    </div>
  );
}

export default function Tutor() {
  const { current } = useModule();
  const cfg = current.config;
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [mode, setMode] = useState("explain");
  const [sub, setSub] = useState("all");
  const [mistakes, setMistakes] = useState([]);
  const [attemptId, setAttemptId] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);

  useEffect(() => {
    api.get(`/tutor/history?module=${current.module}`).then((r) => setMsgs(r.data));
    api.get(`/mistakes?module=${current.module}`).then((r) => setMistakes(r.data));
  }, [current]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = async () => {
    if (mode === "testme") {
      try {
        const { data } = await api.get(`/tutor/test-me?module=${current.module}${sub !== "all" ? `&submodule=${sub}` : ""}`);
        setMsgs((m) => [...m, { role: "assistant", question: data }]);
      } catch (e) { toast.error(errMsg(e)); }
      return;
    }
    if (mode === "mistake" && !attemptId) return toast.error("Choose a mistake to explain");
    if (mode !== "mistake" && !text.trim()) return;
    const userText = text.trim();
    setText("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: userText || "Explain my mistake" }, { role: "assistant", content: "", done: false }]);
    const patch = (fn) => setMsgs((m) => { const c = [...m]; c[c.length - 1] = fn(c[c.length - 1]); return c; });
    try {
      await streamTutor({ message: userText, mode, module: current.module, submodule: sub === "all" ? null : sub.replace(/\(.\)$/, ""), attempt_id: attemptId || null }, (ev) => {
        if (ev.type === "delta") patch((x) => ({ ...x, content: x.content + ev.content }));
        if (ev.type === "done") patch((x) => ({ ...x, done: true, ...ev }));
        if (ev.type === "error") patch((x) => ({ ...x, done: true, content: ev.message }));
      });
    } catch (e) {
      patch((x) => ({ ...x, done: true, content: e.message }));
    } finally { setBusy(false); }
  };

  const clear = async () => { await api.delete(`/tutor/history?module=${current.module}`); setMsgs([]); };

  return (
    <div className="flex flex-col h-[calc(100vh-9rem)]">
      <PageHeader kicker="Source-locked · provisioned course material only" title="AI Tutor">
        <button data-testid="tutor-clear" onClick={clear} className="text-xs text-slate-500 hover:text-rose-300 inline-flex items-center gap-1"><Trash2 size={14} /> Clear</button>
      </PageHeader>
      <div className="flex-1 overflow-y-auto space-y-4 pr-1" data-testid="tutor-thread">
        {!msgs.length && <div className="text-sm text-slate-500 panel p-6">Ask about any Module {cfg.module} topic, e.g. “Explain Ohm's law”. Answers cite the course page; unsupported questions are refused.</div>}
        {msgs.map((m, i) => <Message key={m.message_id || i} m={m} />)}
        <div ref={end} />
      </div>
      <div className="mt-4 panel p-3">
        <div className="flex flex-wrap gap-2 mb-3">
          {MODES.map((x) => (
            <button key={x.id} data-testid={`tutor-mode-${x.id}`} onClick={() => setMode(x.id)}
              className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${mode === x.id ? "border-cyan-400 text-cyan-300 bg-cyan-500/10" : "border-slate-700 text-slate-400 hover:text-slate-100"}`}>{x.label}</button>
          ))}
          <Select value={sub} onValueChange={setSub}>
            <SelectTrigger data-testid="tutor-submodule" className="ml-auto w-[220px] h-8 text-xs bg-slate-900 border-slate-700"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700">
              <SelectItem value="all">All submodules</SelectItem>
              {cfg.submodules.map((s) => <SelectItem key={s.key} value={s.key}>{s.key} {s.title}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        {mode === "mistake" && (
          <Select value={attemptId} onValueChange={setAttemptId}>
            <SelectTrigger data-testid="tutor-mistake-select" className="mb-3 bg-slate-900 border-slate-700 text-xs"><SelectValue placeholder={mistakes.length ? "Select a mistake from your Mistake Bank" : "No mistakes recorded yet"} /></SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700 max-w-xl">
              {mistakes.map((m) => <SelectItem key={m.attempt_id} value={m.attempt_id}>{m.submodule} · {m.question_text.slice(0, 90)}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <div className="flex gap-2">
          <input data-testid="tutor-input" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && !busy && send()}
            disabled={mode === "testme"} placeholder={mode === "testme" ? "Test Me draws a validated question from the bank" : "Ask the source-locked tutor…"}
            className="flex-1 bg-slate-950 border border-slate-700 rounded-md px-4 py-2.5 text-sm outline-none focus:border-cyan-500 disabled:opacity-50" />
          <button data-testid="tutor-send" disabled={busy} onClick={send} className="px-4 rounded-md bg-cyan-500 text-slate-950 hover:bg-cyan-400 disabled:opacity-40 inline-flex items-center gap-2 text-sm font-semibold"><Send size={15} />{mode === "testme" ? "Test me" : "Send"}</button>
        </div>
      </div>
    </div>
  );
}
