import { useEffect, useState } from "react";
import { api, errMsg } from "@/lib/api";
import { StatusPill } from "@/components/Bits";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

export function KnowledgeBaseTab({ status, refresh }) {
  const [files, setFiles] = useState([]);
  const [form, setForm] = useState({ filename: "", document_type: "module_content", module: "", title: "" });
  useEffect(() => { api.get("/admin/files").then((r) => setFiles(r.data)); }, [status]);

  const act = async (fn, msg) => { try { await fn(); toast.success(msg); refresh(); } catch (e) { toast.error(errMsg(e)); } };
  const register = () => act(() => api.post("/admin/documents", { ...form, module: form.module ? Number(form.module) : null }), "Document registered — processing started");

  return (
    <div className="space-y-6">
      <div className="panel overflow-x-auto">
        <table className="w-full text-sm" data-testid="kb-documents-table">
          <thead><tr className="text-left caption border-b border-slate-800">
            <th className="p-3">Document</th><th className="p-3">Type</th><th className="p-3">Module</th><th className="p-3">Version</th><th className="p-3">Provisioned</th><th className="p-3">Processing</th><th className="p-3">Active</th><th className="p-3">Stats</th><th className="p-3" />
          </tr></thead>
          <tbody>
            {status?.documents.map((d) => (
              <tr key={d.document_id} className="border-b border-slate-800/60 align-top" data-testid={`kb-doc-${d.document_type}`}>
                <td className="p-3"><div>{d.title}</div><div className="text-[10px] font-mono text-slate-500">{d.document_id} · {d.filename}</div></td>
                <td className="p-3 font-mono text-xs">{d.document_type}{!d.authoritative && <div className="text-amber-400">non-authoritative</div>}</td>
                <td className="p-3 font-mono">{d.module ?? "—"}</td>
                <td className="p-3 font-mono">v{d.version}</td>
                <td className="p-3 font-mono text-xs text-slate-500">{d.provisioned_at.slice(0, 10)}</td>
                <td className="p-3"><StatusPill status={d.ingestion_status} />{d.ingestion_errors?.length > 0 && <div className="text-[10px] text-rose-400 mt-1">{d.ingestion_errors.join(" ")}</div>}</td>
                <td className="p-3"><StatusPill status={d.active ? "active" : "inactive"} /></td>
                <td className="p-3 text-[10px] font-mono text-slate-400 max-w-[220px]">
                  {d.stats && <>pages {d.stats.page_count}{d.stats.content_chunks != null && ` · ${d.stats.content_chunks} content pages`}{d.stats.detected_category && ` · cat ${d.stats.detected_category}`}{d.stats.example_questions != null && ` · ${d.stats.example_questions} examples`}{d.stats.level_definitions_found != null && ` · level defs ${d.stats.level_definitions_found ? "found" : "missing"}`}</>}
                </td>
                <td className="p-3 whitespace-nowrap space-x-2">
                  <button data-testid={`reingest-${d.document_id}`} onClick={() => act(() => api.post(`/admin/documents/${d.document_id}/ingest`), "Re-processing started")} className="text-xs text-cyan-300 hover:underline">Re-process</button>
                  {!d.active && d.ingestion_status === "completed" && <button data-testid={`activate-doc-${d.document_id}`} onClick={() => act(() => api.post(`/admin/documents/${d.document_id}/activate`), "Version activated")} className="text-xs text-emerald-300 hover:underline">Activate version</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel p-6">
        <div className="caption mb-1">Provision a backend source document</div>
        <p className="text-xs text-slate-500 mb-4">Files must already exist in the backend <span className="font-mono">sources/</span> directory. New versions stay inactive until processed and activated.</p>
        <div className="grid md:grid-cols-5 gap-3">
          <Select value={form.filename} onValueChange={(v) => setForm({ ...form, filename: v })}>
            <SelectTrigger data-testid="kb-file-select" className="bg-slate-900 border-slate-700 text-xs"><SelectValue placeholder="Backend file" /></SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700">{files.map((f) => <SelectItem key={f.filename} value={f.filename}>{f.filename}{f.registered ? " (registered)" : ""}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={form.document_type} onValueChange={(v) => setForm({ ...form, document_type: v })}>
            <SelectTrigger data-testid="kb-type-select" className="bg-slate-900 border-slate-700 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700">
              <SelectItem value="easa_guideline">EASA guideline</SelectItem><SelectItem value="module_content">Module content</SelectItem><SelectItem value="example_questions">Example questions (style ref)</SelectItem>
            </SelectContent>
          </Select>
          <input data-testid="kb-module-input" value={form.module} onChange={(e) => setForm({ ...form, module: e.target.value })} placeholder="Module no." className="bg-slate-900 border border-slate-700 rounded px-3 text-xs" />
          <input data-testid="kb-title-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Document title" className="bg-slate-900 border border-slate-700 rounded px-3 text-xs" />
          <button data-testid="kb-register-button" onClick={register} disabled={!form.filename || !form.title} className="rounded bg-cyan-500 text-slate-950 text-sm font-semibold disabled:opacity-40">Register & process</button>
        </div>
      </div>
    </div>
  );
}

export function AddModuleTab({ status, refresh }) {
  const [module, setModule] = useState("");
  const [doc, setDoc] = useState("");
  const [rep, setRep] = useState(null);
  const contentDocs = (status?.documents || []).filter((d) => d.document_type === "module_content" && d.ingestion_status === "completed");
  const run = async () => {
    try { const { data } = await api.post("/admin/modules/configure", { module: Number(module), content_document_id: doc }); setRep(data); toast.success("Configuration extracted — module kept inactive"); refresh(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="space-y-6">
      <div className="panel p-6">
        <div className="caption mb-1">Add / Configure New Module</div>
        <p className="text-xs text-slate-500 mb-4">Associates processed module content with the EASA guideline, extracts categories, knowledge levels, question counts, time, format and distribution, validates them and keeps the module inactive until confirmation and activation.</p>
        <div className="flex flex-wrap gap-3">
          <input data-testid="add-module-number" value={module} onChange={(e) => setModule(e.target.value)} placeholder="Module number" className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm w-40" />
          <Select value={doc} onValueChange={setDoc}>
            <SelectTrigger data-testid="add-module-doc" className="w-[420px] bg-slate-900 border-slate-700 text-xs"><SelectValue placeholder="Processed module content document" /></SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700">{contentDocs.map((d) => <SelectItem key={d.document_id} value={d.document_id}>M{d.module} · v{d.version} · {d.title}</SelectItem>)}</SelectContent>
          </Select>
          <button data-testid="add-module-run" onClick={run} disabled={!module || !doc} className="px-5 rounded bg-cyan-500 text-slate-950 text-sm font-semibold disabled:opacity-40">Extract & validate</button>
        </div>
      </div>
      {rep && (
        <div className="panel p-6 text-sm" data-testid="add-module-result">
          {Object.entries(rep.summary).map(([k, v]) => <div key={k} className="flex justify-between py-1.5 border-b border-slate-800"><span className="text-slate-400">{k.replace(/_/g, " ")}</span><span className="font-mono">{String(v ?? "—")}</span></div>)}
          <div className="mt-3 text-xs text-slate-500">Category groups: {rep.configs.map((c) => `${c.category_group} (${c.question_count}Q/${c.time_minutes}min, ${c.distribution_status})`).join(" · ")}</div>
        </div>
      )}
    </div>
  );
}
