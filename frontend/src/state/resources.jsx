import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
  useCallback,
} from "react";
import { apiRequest } from "../api/client.js";
import { remainingAt } from "../models/caseView.js";
const Session = createContext(null);
export function useDisplayClock(clock) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return remainingAt(clock, now);
}
export function SessionProvider({ children }) {
  const [persona, setPersona] = useState(
    () => sessionStorage.getItem("cp-studio-persona") || "analyst",
  );
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    Promise.all([
      apiRequest("/health"),
      apiRequest("/v1/ui-config").catch((e) => {
        if (e.status !== 404) throw e;
        return { institution: { name: "CaseProof bank workspace" } };
      }),
    ])
      .then(([health, ui]) => setConfig({ ...ui, health }))
      .catch(setError);
  }, []);
  const change = (value) => {
    sessionStorage.setItem("cp-studio-persona", value);
    setPersona(value);
  };
  return (
    <Session.Provider value={{ persona, setPersona: change, config, error }}>
      {children}
    </Session.Provider>
  );
}
export const useSession = () => useContext(Session);
export function useResource(key, load, interval = 10000) {
  const loader = useRef(load);
  loader.current = load;
  const [state, setState] = useState({
    key,
    data: null,
    error: null,
    loading: true,
    updated: null,
  });
  const [refreshCount, refresh] = useState(0);
  const reload = useCallback(() => refresh((n) => n + 1), []);
  useEffect(() => {
    if(interval === false)return;
    let disposed = false,
      timer,
      controller,
      failures = 0,
      generation = 0;
    setState((old) =>
      old.key === key && old.data
        ? { ...old, loading: false }
        : { key, data: null, error: null, loading: true, updated: null },
    );
    async function run() {
      if (disposed || document.hidden) return;
      controller?.abort();
      controller = new AbortController();
      const current = ++generation;
      let latest;
      try {
        const data = await loader.current(controller.signal);
        if (disposed || current !== generation) return;
        latest = data;
        failures = 0;
        setState({
          key,
          data,
          error: null,
          loading: false,
          updated: new Date().toISOString(),
        });
      } catch (error) {
        if (
          !disposed &&
          current === generation &&
          error.name !== "AbortError"
        ) {
          failures++;
          setState((old) => ({
            key,
            data: [403, 404].includes(error.status)
              ? null
              : old.key === key
                ? old.data
                : null,
            error,
            loading: false,
            updated: old.updated,
          }));
        }
      }
      const delay =
        interval === "case"
          ? latest &&
            (["queued", "running"].includes(latest.workflow?.job?.status) ||
              latest.workflow?.deliveries?.some((d) => d.status === "pending"))
            ? 2000
            : 10000
          : interval;
      if (!disposed && current === generation)
        timer = setTimeout(
          run,
          failures ? Math.min(15000, 2000 * 2 ** (failures - 1)) : delay,
        );
    }
    const focus = () => {
      clearTimeout(timer);
      if (!document.hidden) run();
      else {
        generation++;
        controller?.abort();
      }
    };
    run();
    window.addEventListener("focus", focus);
    document.addEventListener("visibilitychange", focus);
    return () => {
      disposed = true;
      clearTimeout(timer);
      controller?.abort();
      window.removeEventListener("focus", focus);
      document.removeEventListener("visibilitychange", focus);
    };
  }, [key, interval, refreshCount]);
  return {
    ...(state.key === key
      ? state
      : { data: null, error: null, loading: true, updated: null }),
    reload,
  };
}
export function useAction(reload) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(null);
  const locked = useRef(false);
  async function run(action) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      reload?.();
      return result;
    } catch (e) {
      setError(e);
      reload?.();
      throw e;
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  return { busy, error, setError, run };
}
