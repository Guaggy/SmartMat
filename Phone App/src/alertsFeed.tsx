import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AppState } from "react-native";

import { diffAlerts, initialWatch, mayMakeNoise, type WatchState } from "./alertWatch";
import { buzz, ensureLocalPermission, showLocalNotification } from "./push";
import { useApp } from "./state";
import type { Alert } from "./types";

const POLL_MS = 5000;

interface Feed {
  alerts: Alert[] | null; // null until the first answer
  error: boolean;
  refreshing: boolean;
  refresh: () => Promise<void>;
  hidden: ReadonlySet<string>; // alerts hidden from the banner with "Later" (this session only)
  hide: (id: string) => void;
}

const Context = createContext<Feed | null>(null);

/** One shared poll of /api/alerts for the Alerts tab and the banner. Unlike the screens' own polling it keeps going
 *  while the app is in the background for as long as the OS keeps the app alive (a few seconds to minutes), and it
 *  announces each new open alert once: local notification + vibration, unless quiet hours are on. */
export function AlertsFeedProvider({ children }: { children: ReactNode }) {
  const { api, settings, t } = useApp();
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const watch = useRef<WatchState>(initialWatch);
  const live = useRef({ settings, t });
  live.current = { settings, t };

  const run = useCallback(async () => {
    if (!api) return;
    try {
      const { alerts: list } = await api.alerts();
      setAlerts(list);
      setError(false);
      const { fresh, next } = diffAlerts(list, watch.current);
      watch.current = next;
      const { settings: s, t: tr } = live.current;
      if (fresh.length && s.localAlerts && mayMakeNoise(s.quiet, new Date())) {
        buzz();
        for (const a of fresh) {
          const place = a.room ? `${tr("room")} ${a.room}: ` : "";
          showLocalNotification(a.name ?? a.chip_id, place + tr(a.kind === "offline" ? "notifOffline" : "notifHigh"), {
            alert_id: a.id,
            chip_id: a.chip_id,
          });
        }
      }
    } catch {
      setError(true);
    }
  }, [api]);

  useEffect(() => {
    watch.current = initialWatch; // another server (or none): start over silently
    setAlerts(null);
    setError(false);
    setHidden(new Set());
    if (!api) return;
    if (live.current.settings.localAlerts) ensureLocalPermission(); // one prompt, iOS remembers the answer
    run();
    const timer = setInterval(run, POLL_MS);
    const sub = AppState.addEventListener("change", (state) => { if (state === "active") run(); });
    return () => { clearInterval(timer); sub.remove(); };
  }, [api, run]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    await run();
    setRefreshing(false);
  }, [run]);
  const hide = useCallback((id: string) => setHidden((h) => new Set(h).add(id)), []);

  const value = useMemo(() => ({ alerts, error, refreshing, refresh, hidden, hide }), [alerts, error, refreshing, refresh, hidden, hide]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useAlertsFeed(): Feed {
  const value = useContext(Context);
  if (!value) throw new Error("useAlertsFeed must be used inside AlertsFeedProvider");
  return value;
}
