import { useEffect, useState, useCallback } from "react";
import { api, errMsg } from "@/lib/api";
import { useModule } from "@/context/ModuleContext";
import { PageHeader, Empty } from "@/components/Bits";
import { QuestionCard } from "@/components/QuestionCard";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowRight } from "lucide-react";

export default function Practice() {
  const { current } = useModule();
  const cfg = current.config;
  const [sub, setSub] = useState("all");
  const [level, setLevel] = useState("all");
  const [item, setItem] = useState(null);
  const [err, setErr] = useState(null);
  const [answered, setAnswered] = useState(false);
  const [seen, setSeen] = useState([]);
  const [tally, setTally] = useState({ n: 0, c: 0 });

  const next = useCallback(async (excl = []) => {
    setAnswered(false);
    setErr(null);
    const p = new URLSearchParams({ module: current.module, exclude: excl.slice(-15).join(",") });
    if (sub !== "all") p.set("submodule", sub);
    if (level !== "all") p.set("level", level);
    try {
      const { data } = await api.get(`/practice/next?${p}`);
      setItem(data);
    } catch (e) { setItem(null); setErr(errMsg(e)); }
  }, [current, sub, level]);

  useEffect(() => { next([]); }, [next]);

  const onAnswered = (r) => {
    setAnswered(true);
    setSeen((s) => [...s, item.question.question_id]);
    setTally((t) => ({ n: t.n + 1, c: t.c + (r.correct ? 1 : 0) }));
  };

  return (
    <div>
      <PageHeader kicker="Adaptive · weighted by EASA distribution, weakness, repeated errors, recency & coverage" title="Adaptive Practice">
        <div className="font-mono text-sm text-slate-400" data-testid="practice-tally">Session: <span className="text-emerald-400">{tally.c}</span>/{tally.n}</div>
      </PageHeader>
      <div className="flex flex-wrap gap-3 mb-6">
        <Select value={sub} onValueChange={setSub}>
          <SelectTrigger data-testid="practice-submodule" className="w-[280px] bg-slate-900 border-slate-700 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700">
            <SelectItem value="all">Adaptive: all submodules</SelectItem>
            {cfg.submodules.map((s) => <SelectItem key={s.key} value={s.key}>{s.key} {s.title}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={level} onValueChange={setLevel}>
          <SelectTrigger data-testid="practice-level" className="w-[180px] bg-slate-900 border-slate-700 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700">
            <SelectItem value="all">All applicable levels</SelectItem>
            {cfg.applicable_levels.map((l) => <SelectItem key={l} value={String(l)}>EASA Level {l}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {err && <Empty testId="practice-empty">{err}</Empty>}
      {item && (
        <>
          {item.reasons?.length > 0 && <div className="caption mb-3" data-testid="practice-reasons">Selected for: {item.reasons.join(" · ")}</div>}
          <QuestionCard key={item.question.question_id} q={item.question} onAnswered={onAnswered} />
          {answered && (
            <button data-testid="practice-next-button" onClick={() => next(seen)} className="mt-5 inline-flex items-center gap-2 px-5 py-2.5 rounded-md border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10 text-sm transition-colors">
              Next question <ArrowRight size={16} />
            </button>
          )}
        </>
      )}
    </div>
  );
}
