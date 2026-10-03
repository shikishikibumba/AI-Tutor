import { useModule } from "@/context/ModuleContext";
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";

export default function RequireModule({ children }) {
  const { modules, current } = useModule();
  if (modules === null) return <div className="text-slate-500 font-mono text-sm blink">Loading knowledge base…</div>;
  if (!current)
    return (
      <div data-testid="no-active-module" className="panel p-10 max-w-xl">
        <Lock className="text-amber-400 mb-4" />
        <h2 className="text-2xl font-bold mb-2">No module is active yet</h2>
        <p className="text-slate-400 text-sm leading-relaxed">
          Study features unlock once an administrator has processed the provisioned EASA guideline and module course material,
          validated the examination configuration and activated the module. You never need to upload source documents.
        </p>
        <Link to="/admin" className="inline-block mt-5 text-cyan-300 text-sm hover:underline">Administrator console →</Link>
      </div>
    );
  return children;
}
