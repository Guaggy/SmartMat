import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { createApi, type Api } from "./api";
import { defaultSettings, loadSettings, saveSettings, type Settings } from "./settings";
import { t as translate, type StringKey, type Vars } from "./strings";

interface AppState {
  ready: boolean;
  settings: Settings;
  api: Api | null; // null until a server address is saved
  update: (patch: Partial<Settings>) => Promise<void>;
  t: (key: StringKey, vars?: Vars) => string;
}

const Context = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [settings, setSettings] = useState<Settings>(defaultSettings);

  useEffect(() => {
    loadSettings().then((loaded) => {
      setSettings(loaded);
      setReady(true);
    });
  }, []);

  const update = useCallback(
    async (patch: Partial<Settings>) => {
      const next = { ...settings, ...patch };
      setSettings(next);
      await saveSettings(next);
    },
    [settings],
  );

  const api = useMemo(() => (settings.serverUrl ? createApi(settings.serverUrl) : null), [settings.serverUrl]);
  const t = useCallback((key: StringKey, vars?: Vars) => translate(key, settings.lang, vars), [settings.lang]);

  const value = useMemo(() => ({ ready, settings, api, update, t }), [ready, settings, api, update, t]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useApp(): AppState {
  const value = useContext(Context);
  if (!value) throw new Error("useApp must be used inside AppProvider");
  return value;
}
