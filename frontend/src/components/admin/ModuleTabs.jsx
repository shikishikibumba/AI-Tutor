import { api, errMsg } from "@/lib/api";
import { StatusPill } from "@/components/Bits";
import { toast } from "sonner";
import { CheckCircle2, XCircle } from "lucide-react";

const Line = ({ label, value, testId, pill }) => (
  <div className="flex justify-between items-center py-2.5 border-b border-slate-800 text-sm">
    <span className="text-slate-400">{label}</span>
    {pill ? <StatusPill status={value} testId={testId} /> : <span data-testid={testId} className="font-mono text-slate-100">{value ?? "—"}</span>}
  </div>
);

export function OverviewTab({ report, refresh }) {
  if (!report) return <div className="text-slate-500 text-sm">Loading…</div>;
  const s = report.summary;
  const mod = report.module_record;
  const activate = async () => {
    try { await api.post(`/admin/modules/${report.module}/activate`); toast.success("Module activated for students"); refresh(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const deactivate = async () => { await api.post(`/admin/modules/${report.module}/deactivate`); refresh(); };
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div className="panel p-6" data-testid="first-run-report">
        <div className="caption mb-3">First-run processing report · Module {report.module}</div>
        <Line label="Guideline successfully processed" value={s.guideline_processed} pill testId="report-guideline" />
        <Line label={`Module ${report.module} subject content successfully processed`} value={s.content_processed} pill testId="report-content" />
        <Line label="Module detected" value={s.module_detected} testId="report-module" />
        <Line label="Category detected (course material)" value={s.category_detected} testId="report-category" />
        <Line label="Guideline category column" value={s.guideline_category_group} />
        <Line label="Question count detected" value={s.question_count} testId="report-qcount" />
        <Line label="Exam duration detected" value={s.time_minutes ? `${s.time_minutes} minutes` : null} testId="report-time" />
        <Line label="Question format" value={s.format} testId="report-format" />
        <Line label="Pass mark" value={s.pass_mark_percent ? `${s.pass_mark_percent}%` : null} />
        <Line label="Knowledge-level configuration" value={s.knowledge_level_status} pill testId="report-levels" />
        <Line label="Question-distribution configuration" value={s.distribution_status} pill testId="report-distribution" />
      </div>
      <div className="panel p-6">
        <div className="caption mb-3">Activation prerequisites</div>
        {Object.entries(report.prerequisites).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2 py-2 border-b border-slate-800 text-sm" data-testid={`prereq-${k}`}>
            {v ? <CheckCircle2 size={16} className="text-emerald-400" /> : <XCircle size={16} className="text-rose-400" />}
            <span className={v ? "text-slate-200" : "text-slate-400"}>{k.replace(/_/g, " ")}</span>
          </div>
        ))}
        <div className="mt-2 text-xs text-slate-500">Validated questions: <span className="font-mono text-cyan-300">{report.validated_questions}</span></div>
        <div className="mt-6 flex items-center gap-3">
          <span className="text-sm">Module status:</span>
          <StatusPill status={mod?.status || "inactive"} testId="module-status" />
          {mod?.status === "active"
            ? <button data-testid="deactivate-module-button" onClick={deactivate} className="ml-auto px-4 py-2 rounded border border-rose-500/60 text-rose-300 text-sm">Deactivate</button>
            : <button data-testid="activate-module-button" onClick={activate} className="ml-auto px-4 py-2 rounded bg-emerald-500 text-slate-950 font-semibold text-sm hover:bg-emerald-400">Activate module</button>}
        </div>
        {report.module_record?.extraction_issues?.length > 0 && <div className="mt-4 text-xs text-amber-300">{report.module_record.extraction_issues.join("; ")}</div>}
      </div>
    </div>
  );
}

export function ConfigTab({ report, refresh }) {
  const cfg = report?.config;
  if (!cfg) return <div className="panel p-6 text-sm text-slate-400">No configuration extracted for this module.</div>;
  const confirm = async () => {
    try { await api.post(`/admin/configs/${cfg.config_id}/confirm`); toast.success("Configuration confirmed — question generator active"); refresh(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const total = cfg.submodules.reduce((a, s) => a + s.questions, 0);
  return (
    <div className="space-y-6" data-testid="config-confirmation">
      <div className="panel p-6 grid grid-cols-2 md:grid-cols-7 gap-4">
        {[["Module", cfg.module], ["Category", cfg.course_category], ["Questions", cfg.question_count], ["Time", `${cfg.time_minutes} min`], ["Options", cfg.options_per_question], ["Correct answers", cfg.correct_answers], ["Pass mark", `${cfg.pass_mark_percent}%`]].map(([k, v]) => (
          <div key={k}><div className="caption">{k}</div><div className="font-display text-2xl font-bold mt-1" data-testid={`cfg-${k.toLowerCase().replace(/ /g, "-")}`}>{v}</div></div>
        ))}
      </div>
      <div className="panel p-6">
        <div className="caption mb-3">Extraction checks · guideline v{cfg.guideline_version} · source pages: counts p.{cfg.source_pages.counts}, levels p.{cfg.source_pages.levels}, distribution p.{cfg.source_pages.distribution}, syllabus p.{cfg.source_pages.syllabus}, format p.{cfg.source_pages.format}</div>
        <div className="grid md:grid-cols-2 gap-x-6">
          {Object.entries(cfg.checks).map(([k, v]) => (
            <div key={k} className="flex justify-between py-1.5 border-b border-slate-800 text-xs"><span className="text-slate-400">{k.replace(/_/g, " ")}</span><StatusPill status={v} /></div>
          ))}
        </div>
        <div className="mt-3 text-xs text-slate-500 italic">“{cfg.counts_source_text}”</div>
        {cfg.issues.length > 0 && <div className="mt-3 text-xs text-amber-300">{cfg.issues.join(" · ")}</div>}
      </div>
      <div className="panel overflow-x-auto">
        <table className="w-full text-sm" data-testid="distribution-table">
          <thead><tr className="text-left caption border-b border-slate-800">
            <th className="p-3">Submodule</th><th className="p-3">Title</th><th className="p-3 text-right">Questions</th><th className="p-3">Knowledge level</th><th className="p-3">Guideline pages</th><th className="p-3">Syllabus (guideline)</th>
          </tr></thead>
          <tbody>
            {cfg.submodules.map((s) => (
              <tr key={s.key} className="border-b border-slate-800/60 align-top">
                <td className="p-3 font-mono text-cyan-300">{s.key}</td>
                <td className="p-3">{s.title}</td>
                <td className="p-3 text-right font-mono">{s.questions}</td>
                <td className="p-3 font-mono">{s.allowed_levels.join(", ") || "—"}</td>
                <td className="p-3 font-mono text-xs text-slate-500">L p.{s.level_source_page} · D p.{s.distribution_source_page}</td>
                <td className="p-3 text-xs text-slate-400 max-w-md">{s.syllabus || "—"}</td>
              </tr>
            ))}
            <tr className="font-semibold"><td className="p-3" colSpan={2}>TOTAL</td><td className="p-3 text-right font-mono" data-testid="distribution-total">{total}</td><td colSpan={3} /></tr>
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-4">
        <StatusPill status={cfg.status} testId="config-status" />
        {cfg.status !== "confirmed"
          ? <button data-testid="confirm-config-button" onClick={confirm} className="px-6 py-2.5 rounded bg-amber-500 text-slate-950 font-semibold text-sm hover:bg-amber-400">Confirm Configuration</button>
          : <span className="text-xs text-slate-500">Confirmed {cfg.confirmed_at?.slice(0, 16)} by {cfg.confirmed_by}</span>}
      </div>
      <div className="panel p-5">
        <div className="caption mb-2">Other category groups extracted (inactive for this course material)</div>
        {report.configs.filter((c) => !c.applies_to_content).map((c) => (
          <div key={c.config_id} className="text-xs font-mono text-slate-400 py-1">{c.category_group}: {c.question_count} Q · {c.time_minutes} min · levels {c.applicable_levels.join("/")} · {c.distribution_status}</div>
        ))}
      </div>
    </div>
  );
}
