import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const Ctx = createContext(null);

export function ModuleProvider({ children }) {
  const [modules, setModules] = useState(null);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/modules");
      setModules(data);
      setSelected((s) => data.find((m) => m.module === s?.module) || data[0] || null);
    } catch {
      setModules([]);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return <Ctx.Provider value={{ modules, current: selected, setCurrent: setSelected, reload: load }}>{children}</Ctx.Provider>;
}

export const useModule = () => useContext(Ctx);
