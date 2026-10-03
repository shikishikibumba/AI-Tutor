import { useEffect, useState, useCallback, useRef } from "react";
import { api, errMsg } from "@/lib/api";
import { useModule } from "@/context/ModuleContext";
import { PageHeader, LevelBadge } from "@/components/Bits";
import { OptionButton, RevealPanel } from "@/components/QuestionCard";
import { Flag, Timer, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

function StartScreen({ cfg, onStart, history, shortfall }) {
  const threshold = Math.ceil(cfg.question_count * cfg.pass_mark_percent / 100);
  return (
    <div>
      <PageHeader kicker={`Module ${cfg.module} · Category ${cfg.course_category}`} title="Full Mock Examination" />
      <div className="grid lg:grid-cols-3 gap-6">
        <div className="panel p-6 lg:col-span-2">
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div><div className="caption">Questions</div><div className="font-display text-4xl font-bold" data-testid="exam-q-count">{cfg.question_count}</div></div>
            <div><div className="caption">Time</div><div className="font-display text-4xl font-bold" data-testid="exam-time">{cfg.time_minutes}<span className="text-lg text-slate-500"> min</span></div></div>
            <div><div className="caption">Practice threshold</div><div className="font-display text-4xl font-bold text-amber-400" data-testid="exam-threshold">{threshold}/{cfg.question_count}</div></div>
          </div>
          <ul className="text-sm text-slate-400 space-y-1.5 mb-6 list-disc pl-5">
            <li>Paper built from the guideline submodule distribution ({cfg.submodules.length} rows) and permitted EASA knowledge levels.</li>
            <li>{cfg.options_per_question} alternatives per question, exactly {cfg.correct_answers} correct. No penalty marking.</li>
            <li>Timer: {cfg.question_count} × {cfg.seconds_per_question} s = {cfg.time_minutes} minutes; the paper auto-submits at zero.</li>
          </ul>
          <p className="text-xs text-slate-500 border-l-2 border-amber-500/50 pl-3 mb-6">
            The threshold of {threshold}/{cfg.question_count} is a practice representation of the {cfg.pass_mark_percent}% pass mark stated in the provisioned guideline.
            Meeting it in this application does not guarantee passing an official EASA examination.
          </p>
          {shortfall && (
            <div data-testid="exam-shortfall" className="mb-6 text-xs text-amber-300 bg-amber-500/5 border border-amber-500/30 rounded p-3">
              <div className="flex items-center gap-2 mb-2"><AlertTriangle size={14} /> The validated bank does not yet cover the full distribution:</div>
              {shortfall.map((s) => <div key={s.key} className="font-mono">{s.key} {s.title}: {s.available}/{s.required}</div>)}
            </div>
          )}
          <button data-testid="start-exam-button" onClick={onStart} className="px-6 py-3 rounded-md bg-amber-500 text-slate-950 font-semibold hover:bg-amber-400 transition-colors inline-flex items-center gap-2"><Timer size={18} /> Start mock exam</button>
        </div>
        <div className="panel p-6">
          <div className="caption mb-3">Previous attempts</div>
          {history.filter((h) => h.results).length ? history.filter((h) => h.results).map((h) => (
            <div key={h.exam_id} className="flex justify-between py-2 border-b border-slate-800 text-sm font-mono">
              <span className="text-slate-500">{h.submitted_at?.slice(0, 10)}</span>
              <span className={h.results.met_threshold ? "text-emerald-400" : "text-rose-400"}>{h.results.score}/{h.results.total}</span>
            </div>
          )) : <div className="text-sm text-slate-500">None yet.</div>}
        </div>
      </div>
    </div>
  );
}

function Runner({ exam, onSubmitted }) {
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState(exam.answers || {});
  const [flags, setFlags] = useState(exam.flags || []);
  const [left, setLeft] = useState(exam.remaining_seconds);
  const submitting = useRef(false);
  const q = exam.questions[idx];
  const total = exam.questions.length;
  const answered = Object.keys(answers).length;

  const submit = useCallback(async () => {
    if (submitting.current) return;
    submitting.current = true;
    try { const { data } = await api.post(`/exams/${exam.exam_id}/submit`); onSubmitted(data); }
    catch (e) { submitting.current = false; toast.error(errMsg(e)); }
  }, [exam, onSubmitted]);

  useEffect(() => {
    const t = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { if (left === 0) submit(); }, [left, submit]);

  const choose = (l) => {
    setAnswers((a) => ({ ...a, [q.question_id]: l }));
    api.post(`/exams/${exam.exam_id}/answer`, { question_id: q.question_id, selected: l }).catch((e) => toast.error(errMsg(e)));
  };
  const toggleFlag = () => {
    const f = !flags.includes(q.question_id);
    setFlags((x) => (f ? [...x, q.question_id] : x.filter((i) => i !== q.question_id)));
    api.post(`/exams/${exam.exam_id}/answer`, { question_id: q.question_id, flagged: f });
  };
  const elapsed = exam.duration_seconds - left;

  return (
    <div className="grid lg:grid-cols-12 gap-8">
      <div className="lg:col-span-8">
        <div className="panel p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2 mb-5">
            <span className="caption" data-testid="exam-q-index">Question {idx + 1} / {total}</span>
            <span className="font-mono text-xs text-cyan-300">{q.submodule}</span>
            <LevelBadge level={q.knowledge_level} />
            <button data-testid="exam-flag-button" onClick={toggleFlag} className={`ml-auto inline-flex items-center gap-1 text-xs ${flags.includes(q.question_id) ? "text-amber-400" : "text-slate-500"}`}><Flag size={14} /> {flags.includes(q.question_id) ? "Flagged" : "Flag"}</button>
          </div>
          <h2 data-testid="exam-question-text" className="text-lg sm:text-xl leading-relaxed mb-6">{q.question_text}</h2>
          <div className="space-y-3">
            {["A", "B", "C"].map((l) => (
              <OptionButton key={l} letter={l} text={q[`option_${l.toLowerCase()}`]} state={answers[q.question_id] === l ? "selected" : "idle"} onClick={() => choose(l)} testId={`option-${l.toLowerCase()}`} />
            ))}
          </div>
          <div className="flex justify-between mt-8">
            <button data-testid="exam-prev" disabled={idx === 0} onClick={() => setIdx(idx - 1)} className="px-4 py-2 text-sm rounded border border-slate-700 disabled:opacity-30">Previous</button>
            {idx < total - 1
              ? <button data-testid="exam-next" onClick={() => setIdx(idx + 1)} className="px-4 py-2 text-sm rounded bg-cyan-500 text-slate-950 font-semibold">Next</button>
              : <button data-testid="exam-submit-button" onClick={() => window.confirm(`Submit with ${total - answered} unanswered?`) && submit()} className="px-4 py-2 text-sm rounded bg-amber-500 text-slate-950 font-semibold">Submit exam</button>}
          </div>
        </div>
      </div>
      <div className="lg:col-span-4 space-y-4 lg:sticky lg:top-20 self-start">
        <div className="panel p-5">
          <div className="caption">Time remaining</div>
          <div data-testid="exam-timer" className={`font-mono text-5xl font-semibold mt-1 ${left < 300 ? "text-rose-400 blink" : "text-slate-50"}`}>{fmt(left)}</div>
          <div className="grid grid-cols-3 gap-2 mt-4 text-center">
            <div><div className="caption text-[9px]">Answered</div><div data-testid="exam-answered" className="font-mono text-lg text-emerald-400">{answered}</div></div>
            <div><div className="caption text-[9px]">Remaining</div><div data-testid="exam-remaining" className="font-mono text-lg">{total - answered}</div></div>
            <div><div className="caption text-[9px]">Avg / Q</div><div className="font-mono text-lg text-slate-400">{answered ? Math.round(elapsed / answered) : 0}s</div></div>
          </div>
        </div>
        <div className="panel p-3">
          <div className="grid grid-cols-8 gap-1.5 max-h-[300px] overflow-y-auto" data-testid="exam-navigator">
            {exam.questions.map((x, i) => (
              <button key={x.question_id} data-testid={`nav-q-${i + 1}`} onClick={() => setIdx(i)}
                className={`h-8 rounded text-[11px] font-mono border ${i === idx ? "border-cyan-400 text-cyan-300" : flags.includes(x.question_id) ? "border-amber-500 text-amber-300" : answers[x.question_id] ? "border-emerald-600/60 bg-emerald-500/10 text-emerald-300" : "border-slate-800 text-slate-500"}`}>{i + 1}</button>
            ))}
          </div>
        </div>
        <button data-testid="exam-submit-side" onClick={() => window.confirm(`Submit exam? ${total - answered} unanswered.`) && submit()} className="w-full py-2.5 rounded-md border border-amber-500 text-amber-300 text-sm hover:bg-amber-500/10">Submit exam</button>
      </div>
    </div>
  );
}

function Results({ exam, onBack }) {
  const r = exam.results;
  return (
    <div>
      <PageHeader kicker="Mock examination result" title={`${r.score} / ${r.total} · ${r.percent}%`}>
        <button data-testid="exam-back" onClick={onBack} className="px-4 py-2 rounded border border-slate-700 text-sm">Back</button>
      </PageHeader>
      <div className={`panel p-5 mb-6 border-l-4 ${r.met_threshold ? "border-l-emerald-500" : "border-l-rose-500"}`} data-testid="exam-result-banner">
        <div className="font-display text-xl font-semibold">{r.met_threshold ? "Practice threshold met" : "Practice threshold not met"} ({r.threshold}/{r.total})</div>
        <div className="text-xs text-slate-500 mt-1">Practice representation of the {exam.pass_mark_percent}% guideline pass mark — not a guarantee of passing an official EASA examination. Time used: {fmt(r.elapsed_seconds)}.</div>
      </div>
      <div className="grid lg:grid-cols-3 gap-6 mb-8">
        <div className="panel p-5">
          <div className="caption mb-3">By EASA knowledge level</div>
          {Object.entries(r.by_level).map(([l, v]) => (
            <div key={l} className="flex justify-between py-2 border-b border-slate-800"><LevelBadge level={Number(l)} /><span className="font-mono">{v.correct}/{v.total}</span></div>
          ))}
        </div>
        <div className="panel p-5 lg:col-span-2">
          <div className="caption mb-3">By submodule</div>
          <div className="grid sm:grid-cols-2 gap-x-6">
            {r.by_submodule.map((s) => (
              <div key={s.key} className="flex justify-between py-1.5 border-b border-slate-800/60 text-xs">
                <span><span className="font-mono text-cyan-300 mr-2">{s.key}</span>{s.title}</span>
                <span className={`font-mono ${s.correct === s.total ? "text-emerald-400" : s.correct === 0 ? "text-rose-400" : "text-amber-300"}`}>{s.correct}/{s.total}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="caption mb-3">Review</div>
      <div className="space-y-4">
        {exam.review.map((q, i) => (
          <div key={q.question_id} className="panel p-5" data-testid={`review-${i + 1}`}>
            <div className="flex gap-2 items-center mb-2"><span className="caption">Q{i + 1}</span><span className="font-mono text-xs text-cyan-300">{q.submodule}</span><LevelBadge level={q.knowledge_level} /></div>
            <div className="text-sm mb-3">{q.question_text}</div>
            {["A", "B", "C"].map((l) => (
              <div key={l} className={`text-xs py-1 ${l === q.correct_answer ? "text-emerald-300" : l === q.selected ? "text-rose-300 line-through" : "text-slate-400"}`}>{l}. {q[`option_${l.toLowerCase()}`]}</div>
            ))}
            {!q.selected && <div className="text-xs text-amber-300 mt-1">Not answered</div>}
            <RevealPanel result={{ ...q, correct: q.correct }} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MockExam() {
  const { current } = useModule();
  const cfg = current.config;
  const [exam, setExam] = useState(null);
  const [history, setHistory] = useState([]);
  const [shortfall, setShortfall] = useState(null);

  const loadHistory = useCallback(async () => {
    const { data } = await api.get(`/exams?module=${current.module}`);
    setHistory(data);
    const live = data.find((e) => e.status === "in_progress");
    if (live) {
      const { data: full } = await api.get(`/exams/${live.exam_id}`);
      if (full.remaining_seconds > 0) setExam(full);
      else setExam(await api.post(`/exams/${live.exam_id}/submit`).then((r) => r.data));
    }
  }, [current]);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const start = async () => {
    try {
      setShortfall(null);
      const { data } = await api.post(`/exams?module=${current.module}`);
      setExam(data);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.shortfall) setShortfall(d.shortfall);
      toast.error(errMsg(e));
    }
  };

  if (exam?.status === "in_progress") return <Runner exam={exam} onSubmitted={setExam} />;
  if (exam?.status === "submitted") return <Results exam={exam} onBack={() => { setExam(null); loadHistory(); }} />;
  return <StartScreen cfg={cfg} onStart={start} history={history} shortfall={shortfall} />;
}
