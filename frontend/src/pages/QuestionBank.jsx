import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useModule } from "@/context/ModuleContext";
import { PageHeader, LevelBadge, Empty } from "@/components/Bits";
import { QuestionCard } from "@/components/QuestionCard";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

const QTYPES = ["Conceptual", "Terminology", "Numerical calculation", "Schematic/diagram interpretation", "Practical/procedural"];

const F = ({ value, onChange, children, testId, placeholder }) => (
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger data-testid={testId} className="bg-slate-900 border-slate-700 text-xs h-9"><SelectValue placeholder={placeholder} /></SelectTrigger>
    <SelectContent className="bg-slate-900 border-slate-700">{children}</SelectContent>
  </Select>
);

export default function QuestionBank() {
  const { current } = useModule();
  const cfg = current.config;
  const [f, setF] = useState({ submodule: "all", level: "all", question_type: "all", state: "all", topic: "all" });
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);

  const load = useCallback(() => {
    const p = new URLSearchParams({ module: current.module });
    Object.entries(f).forEach(([k, v]) => v !== "all" && p.set(k, v));
    api.get(`/questions?${p}`).then((r) => setData(r.data));
  }, [f, current]);
  useEffect(() => { load(); }, [load]);
  const set = (k) => (v) => setF((x) => ({ ...x, [k]: v }));

  return (
    <div>
      <PageHeader kicker={`Module ${cfg.module} · ${cfg.course_category} · validated questions only`} title="Question Bank" />
      <div className="panel p-4 grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <F value={f.submodule} onChange={set("submodule")} testId="filter-submodule">
          <SelectItem value="all">All submodules</SelectItem>
          {cfg.submodules.map((s) => <SelectItem key={s.key} value={s.key}>{s.key} {s.title}</SelectItem>)}
        </F>
        <F value={f.level} onChange={set("level")} testId="filter-level">
          <SelectItem value="all">All EASA levels</SelectItem>
          {cfg.applicable_levels.map((l) => <SelectItem key={l} value={String(l)}>EASA Level {l}</SelectItem>)}
        </F>
        <F value={f.question_type} onChange={set("question_type")} testId="filter-type">
          <SelectItem value="all">All question types</SelectItem>
          {QTYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
        </F>
        <F value={f.state} onChange={set("state")} testId="filter-state">
          <SelectItem value="all">Any status</SelectItem>
          <SelectItem value="unattempted">Unattempted</SelectItem>
          <SelectItem value="attempted">Attempted</SelectItem>
          <SelectItem value="correct">Last answer correct</SelectItem>
          <SelectItem value="incorrect">Last answer incorrect</SelectItem>
        </F>
        <F value={f.topic} onChange={set("topic")} testId="filter-topic">
          <SelectItem value="all">All topics</SelectItem>
          {(data?.topics || []).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
        </F>
      </div>
      <div className="caption mb-3" data-testid="bank-count">{data ? `${data.questions.length} questions` : "Loading…"}</div>
      {data && !data.questions.length && <Empty testId="bank-empty">No validated questions match these filters.</Empty>}
      <div className="space-y-2">
        {data?.questions.map((q) => (
          <button key={q.question_id} data-testid={`bank-row-${q.question_id}`} onClick={() => setOpen(q)}
            className="w-full text-left panel px-5 py-4 hover:border-cyan-500/50 transition-colors flex flex-col md:flex-row md:items-center gap-3">
            <span className="font-mono text-xs text-cyan-300 w-16 shrink-0">{q.submodule}</span>
            <span className="flex-1 text-sm text-slate-200">{q.question_text}</span>
            <div className="flex items-center gap-2 shrink-0">
              <LevelBadge level={q.knowledge_level} />
              <span className="text-[10px] font-mono text-slate-500 w-28 truncate">{q.question_type}</span>
              <span className="text-[10px] font-mono text-slate-500">p.{q.source_page}</span>
              <span className={`text-[10px] font-mono w-16 text-right ${q.last_result === "correct" ? "text-emerald-400" : q.last_result === "incorrect" ? "text-rose-400" : "text-slate-600"}`}>{q.last_result || "new"}</span>
            </div>
          </button>
        ))}
      </div>
      <Dialog open={!!open} onOpenChange={(o) => { if (!o) { setOpen(null); load(); } }}>
        <DialogContent className="max-w-3xl bg-[#0B0F17] border-slate-800 max-h-[90vh] overflow-y-auto p-0">
          <DialogTitle className="sr-only">Question</DialogTitle>
          {open && <QuestionCard key={open.question_id} q={open} mode="bank" />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
