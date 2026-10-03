import { useEffect, useState, useCallback } from "react";
import { api, errMsg } from "@/lib/api";
import { StatusPill, LevelBadge } from "@/components/Bits";
import { SourceButton } from "@/components/SourceDrawer";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

export function GenerationTab({ report, refresh }) {
  const cfg = report?.config;
  const [jobs, setJobs] = useState([]);
  const [sub, setSub] = useState("");
  const [count, setCount] = useState(3);
  const [sets, setSets] = useState(1);
  const loadJobs = useCallback(() => api.get("/admin/jobs").then((r) => setJobs(r.data)), []);
  useEffect(() => { loadJobs(); const t = setInterval(loadJobs, 5000); return () => clearInterval(t); }, [loadJobs]);
  if (!cfg) return null;
  const go = async (body) => {
    try { await api.post("/admin/generate", { config_id: cfg.config_id, ...body }); toast.success("Generation job started"); loadJobs(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const locked = cfg.status !== "confirmed";
  return (
    <div className="space-y-6">
      {locked && <div className="panel p-4 text-sm text-amber-300" data-testid="gen-locked">The question generator is locked until the configuration is confirmed.</div>}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="panel p-6">
          <div className="caption mb-3">Generate for one submodule</div>
          <div className="flex gap-3">
            <Select value={sub} onValueChange={setSub}>
              <SelectTrigger data-testid="gen-submodule" className="flex-1 bg-slate-900 border-slate-700 text-xs"><SelectValue placeholder="Submodule" /></SelectTrigger>
              <SelectContent className="bg-slate-900 border-slate-700">{cfg.submodules.map((s) => <SelectItem key={s.key} value={s.key}>{s.key} {s.title} (L{s.allowed_levels.join("/")})</SelectItem>)}</SelectContent>
            </Select>
            <input data-testid="gen-count" type="number" min={1} max={15} value={count} onChange={(e) => setCount(Number(e.target.value))} className="w-20 bg-slate-900 border border-slate-700 rounded px-2 text-sm" />
            <button data-testid="gen-submodule-button" disabled={locked || !sub} onClick={() => go({ submodule: sub, count })} className="px-4 rounded bg-cyan-500 text-slate-950 text-sm font-semibold disabled:opacity-40">Generate</button>
          </div>
        </div>
        <div className="panel p-6">
          <div className="caption mb-3">Fill bank to support N full mock exams (EASA distribution)</div>
          <div className="flex gap-3">
            <input data-testid="gen-sets" type="number" min={1} max={12} value={sets} onChange={(e) => setSets(Number(e.target.value))} className="w-20 bg-slate-900 border border-slate-700 rounded px-2 text-sm" />
            <button data-testid="gen-sets-button" disabled={locked} onClick={() => go({ exam_sets: sets })} className="px-4 py-2 rounded bg-amber-500 text-slate-950 text-sm font-semibold disabled:opacity-40">Fill shortfall</button>
          </div>
          <p className="text-[11px] text-slate-500 mt-2">Every candidate passes deterministic checks + an independent source-locked audit. Failures are rejected and regenerated.</p>
        </div>
      </div>
      <div className="space-y-3">
        {jobs.map((j) => (
          <div key={j.job_id} className="panel p-4" data-testid="gen-job">
            <div className="flex items-center gap-3 text-sm mb-2">
              <StatusPill status={j.status === "completed" ? "completed" : j.status} />
              <span className="font-mono text-xs text-slate-500">{j.job_id} · {j.created_at.slice(0, 16)}</span>
              <span className="ml-auto font-mono text-xs"><span className="text-emerald-400">{j.totals?.validated} validated</span> · <span className="text-rose-400">{j.totals?.rejected} rejected</span></span>
            </div>
            <div className="text-[11px] font-mono text-slate-500 max-h-28 overflow-y-auto">{j.log.map((l, i) => <div key={i}>{l.t.slice(11, 19)} {l.msg}</div>)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AuditCard({ q, onDecide }) {
  const [open, setOpen] = useState(false);
  const v = q.validation;
  return (
    <div className="panel p-5" data-testid="audit-question">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <StatusPill status={q.status} />
        <span className="text-[10px] font-mono text-slate-500">VALIDATION {v.status}</span>
        <span className="font-mono text-xs text-cyan-300">{q.submodule}</span>
        <LevelBadge level={q.knowledge_level} />
        <span className="text-[10px] font-mono text-slate-500">{q.question_type} · p.{q.source_page} · {q.question_id}</span>
        <button onClick={() => setOpen(!open)} className="ml-auto text-xs text-cyan-300" data-testid={`audit-toggle-${q.question_id}`}>{open ? "Hide" : "Details"}</button>
      </div>
      <div className="text-sm mb-2">{q.question_text}</div>
      <div className="grid md:grid-cols-3 gap-2 text-xs mb-2">
        {["A", "B", "C"].map((l) => <div key={l} className={l === q.correct_answer ? "text-emerald-300" : "text-slate-400"}>{l}. {q[`option_${l.toLowerCase()}`]}</div>)}
      </div>
      {open && (
        <div className="mt-3 grid lg:grid-cols-2 gap-4 text-xs">
          <div className="space-y-2">
            <div><span className="caption mr-2">Correct</span>{q.correct_answer}</div>
            <div><span className="caption mr-2">Source</span>{q.source_document_title}, page {q.source_page} · {q.source_section}</div>
            <div><span className="caption mr-2">EASA level</span>Level {q.knowledge_level}</div>
            <div><span className="caption mr-2">Level justification</span>{q.level_justification}</div>
            <div><span className="caption mr-2">Quote</span><span className="italic text-slate-400">“{q.supporting_quote}”</span></div>
            {q.formula_if_applicable && <div><span className="caption mr-2">Formula</span><span className="font-mono">{q.formula_if_applicable}</span></div>}
            {q.calculation_steps_if_applicable && <pre className="whitespace-pre-wrap font-mono text-slate-400">{q.calculation_steps_if_applicable}</pre>}
            <div><span className="caption mr-2">Distractors</span>{q.distractors.map((d) => `${d.option}: ${d.error_type}`).join(" · ")}</div>
            {q.source_issue && <div className="text-amber-300">Source issue: {q.source_issue}</div>}
            <SourceButton source={{ document_id: q.source_document_id, document_title: q.source_document_title, page: q.source_page, page_label: q.source_page_label, module: q.module, submodule: q.submodule, section: q.source_section, excerpt: q.supporting_quote, chunk_id: q.source_chunk_id }} testId={`audit-source-${q.question_id}`} />
          </div>
          <div>
            {Object.entries(v.checks).map(([k, c]) => (
              <div key={k} className="py-1 border-b border-slate-800"><div className="flex justify-between"><span className="uppercase font-mono text-[10px] text-slate-400">{k.replace(/_/g, " ")}</span><StatusPill status={c.result} /></div><div className="text-[10px] text-slate-500">{c.note}</div></div>
            ))}
          </div>
        </div>
      )}
      {q.status === "review_required" && (
        <div className="mt-3 flex gap-2">
          <button data-testid={`approve-${q.question_id}`} onClick={() => onDecide(q.question_id, "approve")} className="px-3 py-1.5 rounded bg-emerald-500 text-slate-950 text-xs font-semibold">Approve</button>
          <button data-testid={`reject-${q.question_id}`} onClick={() => onDecide(q.question_id, "reject")} className="px-3 py-1.5 rounded border border-rose-500 text-rose-300 text-xs">Reject</button>
        </div>
      )}
    </div>
  );
}

export function AuditTab({ module }) {
  const [status, setStatus] = useState("all");
  const [qs, setQs] = useState(null);
  const load = useCallback(() => api.get(`/admin/questions?module=${module}${status !== "all" ? `&status=${status}` : ""}`).then((r) => setQs(r.data)), [module, status]);
  useEffect(() => { load(); }, [load]);
  const decide = async (id, decision) => { try { await api.post(`/admin/questions/${id}/decision`, { decision }); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger data-testid="audit-status-filter" className="w-[200px] bg-slate-900 border-slate-700 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700">
            <SelectItem value="all">All statuses</SelectItem><SelectItem value="validated">Validated</SelectItem><SelectItem value="rejected">Rejected</SelectItem><SelectItem value="review_required">Review required</SelectItem>
          </SelectContent>
        </Select>
        <span className="caption">{qs?.length ?? 0} questions</span>
      </div>
      <div className="space-y-3">{qs?.map((q) => <AuditCard key={q.question_id} q={q} onDecide={decide} />)}</div>
    </div>
  );
}

export function FlagsTab({ refresh }) {
  const [flags, setFlags] = useState([]);
  const load = useCallback(() => api.get("/admin/flags").then((r) => setFlags(r.data)), []);
  useEffect(() => { load(); }, [load]);
  const resolve = async (id, resolution) => { await api.post(`/admin/flags/${id}/resolve`, { resolution }); load(); refresh(); };
  if (!flags.length) return <div className="panel p-6 text-sm text-slate-500" data-testid="flags-empty">No open source-inconsistency flags.</div>;
  return (
    <div className="space-y-3">
      {flags.map((f) => (
        <div key={f.flag_id} className="panel p-4 text-sm" data-testid="flag-item">
          <div className="font-mono text-xs text-slate-500 mb-1">{f.submodule} · page {f.page} · {f.question_id || "tutor"} · {f.created_at.slice(0, 16)}</div>
          <div className="text-amber-200">{f.issue}</div>
          <div className="mt-2 flex gap-2">
            <button onClick={() => resolve(f.flag_id, "acknowledged — source preserved")} className="text-xs px-3 py-1 rounded border border-slate-600">Acknowledge (keep source)</button>
            <button onClick={() => resolve(f.flag_id, "source correction required")} className="text-xs px-3 py-1 rounded border border-amber-500 text-amber-300">Mark for source correction</button>
          </div>
        </div>
      ))}
    </div>
  );
}
