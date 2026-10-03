import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useModule } from "@/context/ModuleContext";
import { PageHeader, LevelBadge } from "@/components/Bits";
import { Check, CalendarDays } from "lucide-react";

const TYPE_STYLE = { coverage: "text-cyan-300", revision: "text-amber-300", mixed: "text-fuchsia-300", mock: "text-rose-300" };

export default function StudyPlan() {
  const { current } = useModule();
  const [plan, setPlan] = useState(null);
  const load = useCallback(() => api.get(`/study-plan?module=${current.module}`).then((r) => setPlan(r.data)), [current]);
  useEffect(() => { load(); }, [load]);

  const start = async () => { await api.post(`/study-plan/start?module=${current.module}`, {}); load(); };
  const toggle = async (d) => { await api.post(`/study-plan/day/${d}/toggle?module=${current.module}`); load(); };

  if (!plan) return <div className="text-slate-500 font-mono text-sm blink">Building plan…</div>;
  return (
    <div>
      <PageHeader kicker={`Based on: ${plan.basis}`} title="20-Day Study Plan">
        <div className="flex items-center gap-4">
          {plan.start_date && <div className="font-mono text-sm text-slate-400" data-testid="plan-day">Day <span className="text-cyan-300">{Math.min(Math.max(plan.current_day, 1), 20)}</span>/20 · {plan.days_remaining} days left</div>}
          <button data-testid="plan-start-button" onClick={start} className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-cyan-500 text-cyan-300 text-sm hover:bg-cyan-500/10"><CalendarDays size={15} />{plan.start_date ? "Restart today" : "Start plan today"}</button>
        </div>
      </PageHeader>
      <div className="relative pl-6 border-l border-slate-800 space-y-4">
        {plan.plan.map((d) => (
          <div key={d.day} data-testid={`plan-day-${d.day}`} className={`panel p-5 relative ${plan.current_day === d.day ? "border-cyan-500/60" : ""}`}>
            <button data-testid={`plan-toggle-${d.day}`} onClick={() => toggle(d.day)}
              className={`absolute -left-[37px] top-5 w-6 h-6 rounded-full border grid place-items-center ${d.completed ? "bg-emerald-500 border-emerald-500" : "bg-[#0B0F17] border-slate-600"}`}>
              {d.completed && <Check size={14} className="text-slate-950" />}
            </button>
            <div className="flex flex-wrap items-center gap-3 mb-2">
              <span className="font-mono text-xs text-slate-500">DAY {String(d.day).padStart(2, "0")}{d.date ? ` · ${d.date}` : ""}</span>
              <span className={`caption ${TYPE_STYLE[d.type]}`}>{d.type}</span>
              <span className="font-display font-semibold">{d.title}</span>
            </div>
            {d.items.map((it) => (
              <div key={it.key} className="mt-3 pl-3 border-l border-slate-700">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-mono text-cyan-300 text-xs">{it.key}</span>
                  <span>{it.title}</span>
                  {it.level.map((l) => <LevelBadge key={l} level={l} />)}
                  <span className="text-[10px] font-mono text-slate-500">{it.exam_questions} exam Q</span>
                  {it.accuracy != null && <span className={`text-[10px] font-mono ${it.accuracy >= 75 ? "text-emerald-400" : "text-rose-400"}`}>{it.accuracy}%</span>}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  {it.pages && <>Course PDF pages {it.pages[0]}–{it.pages[1]} · </>}Practice target: {it.practice_target} questions
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">{it.focus}</div>
              </div>
            ))}
            <ul className="mt-3 text-xs text-slate-400 list-disc pl-5 space-y-0.5">{d.tasks.map((t) => <li key={t}>{t}</li>)}</ul>
          </div>
        ))}
      </div>
    </div>
  );
}
