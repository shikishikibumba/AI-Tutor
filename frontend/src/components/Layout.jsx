import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, Bot, Library, Target, Timer, AlertOctagon, CalendarDays, Shield, Zap } from "lucide-react";
import { useModule } from "@/context/ModuleContext";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, id: "nav-dashboard" },
  { to: "/tutor", label: "AI Tutor", icon: Bot, id: "nav-tutor" },
  { to: "/bank", label: "Question Bank", icon: Library, id: "nav-bank" },
  { to: "/practice", label: "Adaptive Practice", icon: Target, id: "nav-practice" },
  { to: "/exam", label: "Mock Exam", icon: Timer, id: "nav-exam" },
  { to: "/mistakes", label: "Mistake Bank", icon: AlertOctagon, id: "nav-mistakes" },
  { to: "/plan", label: "20-Day Plan", icon: CalendarDays, id: "nav-plan" },
];

export default function Layout() {
  const { modules, current, setCurrent } = useModule();
  return (
    <div className="min-h-screen flex bg-[#0B0F17]">
      <aside className="hidden lg:flex w-64 shrink-0 flex-col border-r border-slate-800 bg-[#0A0E15] sticky top-0 h-screen">
        <div className="px-6 py-6 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded bg-amber-500 grid place-items-center"><Zap size={18} className="text-slate-950" /></div>
            <div>
              <div className="font-display font-bold leading-tight">Part-66</div>
              <div className="caption text-[9px]">AI Study Assistant</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 py-4 px-3 space-y-1">
          {NAV.map(({ to, label, icon: Icon, id }) => (
            <NavLink key={to} to={to} end={to === "/"} data-testid={id}
              className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors ${isActive ? "bg-cyan-500/10 text-cyan-300 border-l-2 border-cyan-400" : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/50"}`}>
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-slate-800 space-y-3">
          <div className="text-[10px] font-mono text-emerald-400/80 leading-relaxed">● SOURCE-LOCKED<br />No internet · provisioned sources only</div>
          <NavLink to="/admin" data-testid="nav-admin" className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-200"><Shield size={14} /> Admin console</NavLink>
        </div>
      </aside>
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="sticky top-0 z-30 backdrop-blur-md bg-[#0B0F17]/90 border-b border-slate-800 px-4 sm:px-8 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 lg:hidden overflow-x-auto">
            {NAV.map(({ to, icon: Icon, id }) => (
              <NavLink key={to} to={to} end={to === "/"} data-testid={`m-${id}`} className={({ isActive }) => `p-2 rounded ${isActive ? "text-cyan-300" : "text-slate-500"}`}><Icon size={18} /></NavLink>
            ))}
          </div>
          <div className="hidden lg:block caption">EASA Part-66 · Basic Knowledge · Examination Standard</div>
          {modules?.length > 0 && (
            <Select value={String(current?.module)} onValueChange={(v) => setCurrent(modules.find((m) => String(m.module) === v))}>
              <SelectTrigger data-testid="module-selector" className="w-auto min-w-[240px] bg-slate-900 border-slate-700 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-slate-900 border-slate-700">
                {modules.map((m) => (
                  <SelectItem key={m.module} value={String(m.module)}>Module {m.module} · {m.title} · {m.category}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </header>
        <main className="flex-1 grid-bg">
          <div className="max-w-6xl mx-auto px-4 sm:px-8 py-8 sm:py-10"><Outlet /></div>
        </main>
      </div>
    </div>
  );
}
