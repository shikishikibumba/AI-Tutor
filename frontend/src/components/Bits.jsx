export const LevelBadge = ({ level, testId }) => {
  const cls = level === 1 ? "border-sky-500/40 text-sky-300 bg-sky-500/10" : level === 2 ? "border-amber-500/40 text-amber-300 bg-amber-500/10" : "border-fuchsia-500/40 text-fuchsia-300 bg-fuchsia-500/10";
  return (
    <span data-testid={testId} className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono tracking-widest border ${cls}`}>
      EASA LEVEL {level}
    </span>
  );
};

export const StatusPill = ({ status, testId }) => {
  const ok = ["VALID", "PASS", "YES", "validated", "completed", "active", "confirmed", true].includes(status);
  const bad = ["INVALID", "FAIL", "NO", "rejected", "failed", false].includes(status);
  const cls = ok ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10" : bad ? "border-rose-500/40 text-rose-300 bg-rose-500/10" : "border-amber-500/40 text-amber-300 bg-amber-500/10";
  const label = status === true ? "PASS" : status === false ? "FAIL" : String(status ?? "—");
  return <span data-testid={testId} className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono tracking-widest border uppercase ${cls}`}>{label}</span>;
};

export const PageHeader = ({ kicker, title, children }) => (
  <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8 fade-up">
    <div>
      <div className="caption text-cyan-400">{kicker}</div>
      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mt-1">{title}</h1>
    </div>
    {children}
  </div>
);

export const Empty = ({ children, testId }) => (
  <div data-testid={testId} className="panel p-8 text-center text-slate-400 text-sm">{children}</div>
);
