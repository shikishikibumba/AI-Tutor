import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useModule } from "@/context/ModuleContext";
import { PageHeader, LevelBadge, Empty } from "@/components/Bits";
import { SourceButton } from "@/components/SourceDrawer";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Repeat } from "lucide-react";

const TYPES = ["Concept misunderstanding", "Formula error", "Calculation error", "Unit conversion", "Sign error", "Misinterpretation", "Recall error", "Series/parallel confusion", "Other"];

export default function Mistakes() {
  const { current } = useModule();
  const cfg = current.config;
  const [items, setItems] = useState(null);
  const [ins, setIns] = useState(null);
  const [sub, setSub] = useState("all");
  const [type, setType] = useState("all");

  useEffect(() => {
    const p = new URLSearchParams({ module: current.module });
    if (sub !== "all") p.set("submodule", sub);
    if (type !== "all") p.set("mistake_type", type);
    api.get(`/mistakes?${p}`).then((r) => setItems(r.data));
    api.get(`/mistakes/insights?module=${current.module}`).then((r) => setIns(r.data));
  }, [current, sub, type]);

  return (
    <div>
      <PageHeader kicker="Every incorrect answer, classified by mistake type" title="Mistake Bank" />
      {ins && (
        <div className="grid lg:grid-cols-3 gap-6 mb-8">
          <div className="panel p-5 lg:col-span-2">
            <div className="caption mb-3">Pattern insights</div>
            {ins.groups.length ? ins.groups.slice(0, 6).map((g) => (
              <div key={`${g.submodule}-${g.level}`} data-testid="mistake-insight" className={`mb-3 pl-3 border-l-2 ${g.repeated ? "border-rose-500" : "border-slate-700"}`}>
                <div className="text-sm font-medium">{g.submodule} {g.title} — Level {g.level}</div>
                <div className="text-xs text-slate-400">{g.message}</div>
              </div>
            )) : <div className="text-sm text-slate-500">No patterns yet.</div>}
          </div>
          <div className="panel p-5">
            <div className="caption mb-3">By mistake type</div>
            {Object.entries(ins.type_totals).map(([k, v]) => (
              <div key={k} className="flex justify-between text-xs py-1.5 border-b border-slate-800"><span>{k}</span><span className="font-mono text-rose-300">{v}</span></div>
            ))}
            <div className="mt-3 text-xs text-slate-500 flex items-center gap-1"><Repeat size={12} /> {ins.repeated_questions} question(s) missed more than once</div>
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-3 mb-5">
        <Select value={sub} onValueChange={setSub}>
          <SelectTrigger data-testid="mistakes-filter-submodule" className="w-[260px] bg-slate-900 border-slate-700 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700">
            <SelectItem value="all">All submodules</SelectItem>
            {cfg.submodules.map((s) => <SelectItem key={s.key} value={s.key}>{s.key} {s.title}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger data-testid="mistakes-filter-type" className="w-[220px] bg-slate-900 border-slate-700 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700">
            <SelectItem value="all">All mistake types</SelectItem>
            {TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {items && !items.length && <Empty testId="mistakes-empty">No mistakes recorded for this selection.</Empty>}
      <div className="space-y-4">
        {items?.map((m) => (
          <div key={m.attempt_id} data-testid="mistake-item" className="panel p-5">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="font-mono text-xs text-cyan-300">{m.submodule}</span>
              <span className="text-xs text-slate-400">{m.topic}</span>
              <LevelBadge level={m.knowledge_level} />
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-rose-500/40 text-rose-300">{m.mistake_type}</span>
              {m.times_wrong > 1 && <span className="text-[10px] font-mono text-amber-300">missed ×{m.times_wrong}</span>}
              <span className="ml-auto text-[10px] font-mono text-slate-500">{m.created_at.slice(0, 16).replace("T", " ")} · {m.mode}</span>
            </div>
            <div className="text-sm mb-3">{m.question_text}</div>
            <div className="grid sm:grid-cols-2 gap-2 text-xs mb-3">
              <div className="text-rose-300">Your answer: {m.selected}. {m[`option_${m.selected.toLowerCase()}`]}</div>
              <div className="text-emerald-300">Correct: {m.correct_answer}. {m[`option_${m.correct_answer.toLowerCase()}`]}</div>
            </div>
            <p className="text-xs text-slate-400 mb-3">{m.explanation}</p>
            <SourceButton source={m.source} testId={`mistake-source-${m.attempt_id}`} />
          </div>
        ))}
      </div>
    </div>
  );
}
