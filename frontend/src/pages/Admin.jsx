import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api, errMsg } from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Shield, LogOut, ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { useModule } from "@/context/ModuleContext";
import { OverviewTab, ConfigTab } from "@/components/admin/ModuleTabs";
import { KnowledgeBaseTab, AddModuleTab } from "@/components/admin/KnowledgeBase";
import { GenerationTab, AuditTab, FlagsTab } from "@/components/admin/QuestionTabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

function Login({ onDone }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      const { data } = await api.post("/auth/login", { email, password });
      localStorage.setItem("admin_token", data.token);
      onDone(data.user);
    } catch (e2) { setErr(errMsg(e2)); }
  };
  return (
    <div className="min-h-screen grid place-items-center grid-bg px-4">
      <form onSubmit={submit} className="panel p-8 w-full max-w-sm fade-up" data-testid="admin-login-form">
        <Shield className="text-amber-400 mb-4" />
        <h1 className="text-2xl font-bold mb-1">Administrator</h1>
        <p className="text-xs text-slate-500 mb-6">Knowledge-base provisioning, configuration validation and module activation.</p>
        <input data-testid="admin-email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" className="w-full mb-3 bg-slate-950 border border-slate-700 rounded px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
        <input data-testid="admin-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" className="w-full mb-4 bg-slate-950 border border-slate-700 rounded px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
        {err && <div data-testid="admin-login-error" className="text-xs text-rose-400 mb-3">{err}</div>}
        <button data-testid="admin-login-submit" className="w-full py-2.5 rounded bg-cyan-500 text-slate-950 font-semibold text-sm hover:bg-cyan-400">Sign in</button>
        <Link to="/" className="block text-center text-xs text-slate-500 mt-4 hover:text-slate-300">← Back to study app</Link>
      </form>
    </div>
  );
}

export default function Admin() {
  const [user, setUser] = useState(undefined);
  const [status, setStatus] = useState(null);
  const [module, setModule] = useState(3);
  const [report, setReport] = useState(null);
  const { reload } = useModule();

  useEffect(() => {
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => setUser(null));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([api.get("/admin/status"), api.get(`/admin/modules/${module}/report`)]);
      setStatus(s.data);
      setReport(r.data);
      reload();
    } catch (e) { toast.error(errMsg(e)); }
  }, [module, reload]);

  useEffect(() => { if (user) refresh(); }, [user, refresh]);

  if (user === undefined) return <div className="p-10 text-slate-500 font-mono text-sm">Checking session…</div>;
  if (!user) return <Login onDone={setUser} />;

  const logout = async () => { await api.post("/auth/logout"); localStorage.removeItem("admin_token"); setUser(null); };

  return (
    <div className="min-h-screen grid-bg">
      <header className="sticky top-0 z-30 backdrop-blur-md bg-[#0B0F17]/90 border-b border-slate-800 px-6 h-14 flex items-center gap-4">
        <Link to="/" className="text-slate-500 hover:text-slate-200" data-testid="admin-back"><ArrowLeft size={18} /></Link>
        <Shield size={18} className="text-amber-400" />
        <span className="font-display font-semibold">Admin · Knowledge Base & Validation</span>
        <Select value={String(module)} onValueChange={(v) => setModule(Number(v))}>
          <SelectTrigger data-testid="admin-module-select" className="ml-6 w-[200px] h-8 bg-slate-900 border-slate-700 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700">
            {(status?.modules?.length ? status.modules : [{ module: 3, title: "ELECTRICAL FUNDAMENTALS", status: "inactive" }]).map((m) => (
              <SelectItem key={m.module} value={String(m.module)}>Module {m.module} · {m.status}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-xs text-slate-500 font-mono">{user.email}</span>
        <button data-testid="admin-logout" onClick={logout} className="text-slate-500 hover:text-rose-300"><LogOut size={16} /></button>
      </header>
      <div className="max-w-7xl mx-auto px-6 py-8">
        <Tabs defaultValue="overview">
          <TabsList className="bg-slate-900 border border-slate-800 mb-6 flex-wrap h-auto">
            {[["overview", "First-run report"], ["config", "Configuration"], ["kb", "Knowledge base"], ["gen", "Generation"], ["audit", "Question audit"], ["flags", `Flags${status?.open_flags ? ` (${status.open_flags})` : ""}`], ["add", "Add / Configure module"]].map(([v, l]) => (
              <TabsTrigger key={v} value={v} data-testid={`admin-tab-${v}`} className="text-xs data-[state=active]:bg-cyan-500/15 data-[state=active]:text-cyan-300">{l}</TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="overview"><OverviewTab report={report} refresh={refresh} /></TabsContent>
          <TabsContent value="config"><ConfigTab report={report} refresh={refresh} /></TabsContent>
          <TabsContent value="kb"><KnowledgeBaseTab status={status} refresh={refresh} /></TabsContent>
          <TabsContent value="gen"><GenerationTab report={report} refresh={refresh} /></TabsContent>
          <TabsContent value="audit"><AuditTab module={module} /></TabsContent>
          <TabsContent value="flags"><FlagsTab refresh={refresh} /></TabsContent>
          <TabsContent value="add"><AddModuleTab status={status} refresh={refresh} /></TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
