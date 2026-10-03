import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useModule } from "@/context/ModuleContext";
import { PageHeader, LevelBadge } from "@/components/Bits";
import { Timer, Bot, Target, ArrowUpRight } from "lucide-react";

const Stat = ({ label, value, sub, testId, tone = "text-slate-50" }) => (
  <div className="panel p-5">
    <div className="caption">{label}</div>
    <div data-testid={testId} className={`font-display text-4xl font-bold mt-2 ${tone}`}>{value}</div>
    {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
  </div>
);

export default function Dashboard() {
  const { current } = useModule();
  const cfg = current.config;
  const [perf, setPerf] = useState(null);
  const [ready, setReady] = useState(null);
  const [ins, setIns] = useState(null);

  useEffect(() => {
    const m = current.module;
    api.get(`/performance?module=${m}`).then((r) => setPerf(r.data));
    api.get(`/modules/${m}/bank-readiness`).then((r) => setReady(r.data));
    api.get(`/mistakes/insights?module=${m}`).then((r) => setIns(r.data));
  }, [current]);

  return (
    <div>
      <PageHeader kicker={`Module ${cfg.module} · Category ${cfg.course_category}`} title={cfg.module_title.replace(/\b\w+/g, (w) => w[0] + w.slice(1).toLowerCase())}>
        <div className="flex gap-3">
          <Link to="/exam" data-testid="dash-start-exam" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-amber-500 text-slate-950 font-semibold text-sm hover:bg-amber-400 transition-colors"><Timer size={16} /> Mock exam</Link>
          <Link to="/practice" data-testid="dash-practice" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md border border-slate-700 text-sm hover:border-cyan-500 transition-colors"><Target size={16} /> Practice</Link>
        </div>
      </PageHeader>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Stat label="Exam format" value={`${cfg.question_count} Q`} sub={`${cfg.time_minutes} min · ${cfg.options_per_question} options · ${cfg.correct_answers} correct`} testId="dash-exam-format" />
        <Stat label="Practice threshold" value={`${Math.ceil(cfg.question_count * cfg.pass_mark_percent / 100)}/${cfg.question_count}`} sub={`${cfg.pass_mark_percent}% pass mark (guideline)`} testId="dash-threshold" tone="text-amber-400" />
        <Stat label="Validated questions" value={ready?.total_validated ?? "—"} sub={ready?.ready ? "Full mock exam available" : "Bank still growing"} testId="dash-validated" tone="text-cyan-300" />
        <Stat label="Answered" value={perf?.total_attempts ?? "—"} sub={perf?.total_attempts ? `${Math.round(100 * perf.total_correct / perf.total_attempts)}% correct overall` : "No attempts yet"} testId="dash-attempts" />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="panel p-6 lg:col-span-1">
          <div className="caption mb-4">Performance by EASA knowledge level</div>
          {perf && perf.applicable_levels.map((lv) => {
            const d = perf.levels[String(lv)];
            return (
              <div key={lv} className="mb-5" data-testid={`level-perf-${lv}`}>
                <div className="flex justify-between items-center mb-2">
                  <LevelBadge level={lv} />
                  <span className="font-mono text-lg">{d.percent == null ? "—" : `${d.percent}%`}</span>
                </div>
                <div className="h-1.5 bg-slate-800 rounded"><div className="h-full bg-cyan-400 rounded transition-all" style={{ width: `${d.percent || 0}%` }} /></div>
                <div className="text-[11px] text-slate-500 mt-1 font-mono">{d.correct}/{d.attempts} correct</div>
              </div>
            );
          })}
          {perf && [1, 2, 3].filter((l) => !perf.applicable_levels.includes(l)).map((l) => (
            <div key={l} className="text-xs text-slate-500 font-mono">Level {l}: not applicable to this module/category (guideline)</div>
          ))}
        </div>

        <div className="panel p-6 lg:col-span-2">
          <div className="flex justify-between items-center mb-4">
            <div className="caption">Submodule coverage · EASA weighting</div>
            <Link to="/plan" className="text-xs text-cyan-300 inline-flex items-center gap-1">Study plan <ArrowUpRight size={12} /></Link>
          </div>
          <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2">
            {perf?.submodules.map((s) => (
              <div key={s.key} data-testid={`sub-perf-${s.key}`} className="flex items-center gap-3 py-1.5 border-b border-slate-800/60">
                <span className="font-mono text-xs text-cyan-300 w-14">{s.key}</span>
                <span className="text-xs text-slate-300 flex-1 truncate" title={s.title}>{s.title}</span>
                <span className="text-[10px] font-mono text-slate-500">L{s.level.join("/")}·{s.weight}Q</span>
                <span className={`font-mono text-xs w-10 text-right ${s.percent == null ? "text-slate-600" : s.percent >= 75 ? "text-emerald-400" : "text-rose-400"}`}>{s.percent == null ? "—" : `${Math.round(s.percent)}%`}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mt-6">
        <div className="panel p-6">
          <div className="caption mb-4">Repeated mistake patterns</div>
          {ins?.groups?.length ? ins.groups.slice(0, 4).map((g) => (
            <div key={`${g.submodule}-${g.level}`} className="mb-3 border-l-2 border-rose-500/60 pl-3" data-testid="dash-insight">
              <div className="text-sm font-medium">{g.submodule} {g.title} — Level {g.level}</div>
              <div className="text-xs text-slate-400">{g.message}</div>
            </div>
          )) : <div className="text-sm text-slate-500">No mistakes recorded yet.</div>}
        </div>
        <div className="panel p-6 flex flex-col justify-between">
          <div>
            <div className="caption mb-2">Source-locked tutor</div>
            <p className="text-sm text-slate-400 leading-relaxed">Every explanation is retrieved from the provisioned Module {cfg.module} course notes and cites the exact page. If the notes don’t cover something, the tutor says so instead of guessing.</p>
          </div>
          <Link to="/tutor" data-testid="dash-tutor" className="mt-5 inline-flex items-center gap-2 text-cyan-300 text-sm"><Bot size={16} /> Open AI Tutor</Link>
        </div>
      </div>
    </div>
  );
}
