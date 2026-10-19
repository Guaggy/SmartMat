import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

/** Calls `load` now and every `intervalMs` while the app is in the foreground. Keeps the last data on errors.
 *  `key` identifies the data source (e.g. server address + mat id); data is cleared when it changes. */
export function usePoll<T>(load: (() => Promise<T>) | null, key: string, intervalMs = 5000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const loadRef = useRef(load);
  loadRef.current = load;
  const active = load !== null;

  const run = useCallback(async () => {
    const current = loadRef.current;
    if (!current) return;
    try {
      setData(await current());
      setError(null);
    } catch (e) {
      setError(e as Error);
    }
  }, []);

  useEffect(() => {
    if (!active) return;
    setData(null);
    run();
    let timer: ReturnType<typeof setInterval> | undefined;
    const start = () => { timer = setInterval(run, intervalMs); };
    const stop = () => { if (timer) clearInterval(timer); timer = undefined; };
    start();
    const sub = AppState.addEventListener("change", (state) => {
      stop();
      if (state === "active") { run(); start(); }
    });
    return () => { stop(); sub.remove(); };
  }, [active, key, intervalMs, run]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    await run();
    setRefreshing(false);
  }, [run]);

  return { data, error, refreshing, refresh };
}
