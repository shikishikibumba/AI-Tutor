import { useEffect, useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api, pageImageUrl } from "@/lib/api";
import { FileText, ShieldCheck } from "lucide-react";

const Row = ({ label, value, testId }) => (
  <div className="flex justify-between gap-4 py-2 border-b border-slate-800/70 text-sm">
    <span className="caption">{label}</span>
    <span data-testid={testId} className="text-right text-slate-200 font-mono text-xs">{value ?? "—"}</span>
  </div>
);

export const SourceButton = ({ source, testId = "source-button", label = "SOURCE" }) => {
  const [open, setOpen] = useState(false);
  if (!source) return null;
  return (
    <>
      <button
        data-testid={testId}
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/10 transition-colors text-[11px] font-mono tracking-widest"
      >
        <FileText size={12} /> {label}
      </button>
      <SourceDrawer open={open} onOpenChange={setOpen} source={source} />
    </>
  );
};

export function SourceDrawer({ open, onOpenChange, source }) {
  const [chunk, setChunk] = useState(null);
  useEffect(() => {
    if (open && source?.chunk_id) api.get(`/sources/chunk/${source.chunk_id}`).then((r) => setChunk(r.data)).catch(() => setChunk(null));
  }, [open, source]);
  const docId = source?.document_id || chunk?.document_id;
  const page = source?.page || chunk?.page_number;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid="source-drawer" className="w-full sm:max-w-xl bg-[#0E1420] border-slate-800 overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2 text-slate-100">
            <ShieldCheck size={18} className="text-emerald-400" /> Source traceability
          </SheetTitle>
        </SheetHeader>
        <div className="mt-4">
          <Row label="Document" value={source?.document_title || chunk?.document_title} testId="source-doc-name" />
          <Row label="PDF page" value={page} testId="source-page" />
          <Row label="Course page label" value={source?.page_label ?? chunk?.page_label} />
          <Row label="Module" value={source?.module ?? chunk?.module} />
          <Row label="Submodule" value={source?.submodule ?? chunk?.submodule} testId="source-submodule" />
          <Row label="Section" value={source?.section || chunk?.section} testId="source-section" />
        </div>
        {source?.excerpt && (
          <div className="mt-5">
            <div className="caption mb-2">Supporting excerpt (verbatim)</div>
            <blockquote data-testid="source-excerpt" className="border-l-2 border-amber-500 pl-3 text-sm text-slate-300 italic">“{source.excerpt}”</blockquote>
          </div>
        )}
        {docId && page && (
          <div className="mt-5">
            <div className="caption mb-2">Original page</div>
            <img data-testid="source-page-image" src={pageImageUrl(docId, page)} alt={`Source page ${page}`} className="w-full rounded border border-slate-800 bg-white" />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
