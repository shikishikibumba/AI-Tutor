import { useState } from "react";
import { api, errMsg } from "@/lib/api";
import { LevelBadge } from "@/components/Bits";
import { SourceButton } from "@/components/SourceDrawer";
import { CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

export const OptionButton = ({ letter, text, state, onClick, disabled, testId }) => {
  const base = "w-full text-left flex gap-4 items-start p-4 rounded-md border transition-colors duration-200";
  const cls = {
    idle: "border-slate-800 bg-slate-900/40 hover:border-cyan-500/50 hover:bg-cyan-500/5",
    selected: "border-cyan-500 bg-cyan-500/10",
    correct: "border-emerald-500 bg-emerald-500/10",
    wrong: "border-rose-500 bg-rose-500/10",
    dim: "border-slate-800 bg-slate-900/20 opacity-60",
  }[state];
  return (
    <button data-testid={testId} disabled={disabled} onClick={onClick} className={`${base} ${cls}`}>
      <span className="font-mono text-sm w-7 h-7 shrink-0 grid place-items-center rounded border border-slate-700 text-slate-300">{letter}</span>
      <span className="text-[15px] leading-relaxed text-slate-100 pt-0.5">{text}</span>
    </button>
  );
};

export function RevealPanel({ result }) {
  return (
    <div data-testid="answer-reveal" className="mt-6 panel p-5 fade-up">
      <div className="flex items-center gap-2 mb-3">
        {result.correct ? <CheckCircle2 className="text-emerald-400" size={20} /> : <XCircle className="text-rose-400" size={20} />}
        <span data-testid="answer-result" className={`font-display font-semibold ${result.correct ? "text-emerald-300" : "text-rose-300"}`}>
          {result.correct ? "Correct" : `Incorrect — correct answer ${result.correct_answer}`}
        </span>
        {!result.correct && result.mistake_type && (
          <span data-testid="mistake-type" className="ml-2 text-[10px] font-mono tracking-widest px-2 py-0.5 rounded-full border border-rose-500/40 text-rose-300">{result.mistake_type}</span>
        )}
      </div>
      <p data-testid="answer-explanation" className="text-sm text-slate-300 leading-relaxed">{result.explanation}</p>
      {result.formula && <div className="mt-3 font-mono text-sm text-cyan-300 bg-cyan-500/5 border border-cyan-500/20 rounded px-3 py-2">{result.formula}</div>}
      {result.calculation_steps && <pre className="mt-3 whitespace-pre-wrap font-mono text-xs text-slate-300 bg-slate-950/60 border border-slate-800 rounded p-3">{result.calculation_steps}</pre>}
      {result.level_justification && <p className="mt-3 text-xs text-slate-400"><span className="caption mr-2">Level basis</span>{result.level_justification}</p>}
      {result.source_issue && (
        <div className="mt-3 flex gap-2 text-xs text-amber-300 bg-amber-500/5 border border-amber-500/30 rounded p-2">
          <AlertTriangle size={14} /> Source flag: {result.source_issue}
        </div>
      )}
      <div className="mt-4 flex items-center gap-3">
        <SourceButton source={result.source} testId="answer-source-button" />
        <span className="text-xs text-slate-500 font-mono">{result.source?.document_title} · p.{result.source?.page}</span>
      </div>
    </div>
  );
}

export function QuestionCard({ q, mode = "practice", onAnswered, index }) {
  const [sel, setSel] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/questions/${q.question_id}/attempt`, { selected: sel, mode });
      setResult(data);
      onAnswered?.(data);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const state = (l) => {
    if (!result) return sel === l ? "selected" : "idle";
    if (l === result.correct_answer) return "correct";
    if (l === result.selected) return "wrong";
    return "dim";
  };

  return (
    <div data-testid="question-card" className="panel p-6 sm:p-8 fade-up">
      <div className="flex flex-wrap items-center gap-2 mb-5">
        {index && <span className="caption">Q{index}</span>}
        <span className="font-mono text-xs text-cyan-300">{q.submodule}</span>
        <span className="text-xs text-slate-400">{q.submodule_title}</span>
        <LevelBadge level={q.knowledge_level} testId="question-level" />
        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">{q.question_type}</span>
      </div>
      <h2 data-testid="question-text" className="text-lg sm:text-xl leading-relaxed text-slate-50 mb-6 font-medium">{q.question_text}</h2>
      <div className="space-y-3">
        {["A", "B", "C"].map((l) => (
          <OptionButton key={l} letter={l} text={q[`option_${l.toLowerCase()}`]} state={state(l)} disabled={!!result}
            onClick={() => setSel(l)} testId={`option-${l.toLowerCase()}`} />
        ))}
      </div>
      {!result && (
        <button data-testid="submit-answer-button" disabled={!sel || busy} onClick={submit}
          className="mt-6 px-6 py-2.5 rounded-md bg-cyan-500 text-slate-950 font-semibold text-sm hover:bg-cyan-400 disabled:opacity-40 transition-colors">
          {busy ? "Checking…" : "Submit answer"}
        </button>
      )}
      {result && <RevealPanel result={result} />}
    </div>
  );
}
