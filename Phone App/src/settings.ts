import * as SecureStore from "expo-secure-store";

import { defaultLang, type Lang } from "./strings";

export interface Settings {
  serverUrl: string;
  lang: Lang;
}

const KEY = "smartmat.settings";
export const defaultSettings: Settings = { serverUrl: "", lang: defaultLang };

// Server address and language only. The PIN is never stored: it is asked for on every alert action.
export async function loadSettings(): Promise<Settings> {
  try {
    const raw = await SecureStore.getItemAsync(KEY);
    if (!raw) return defaultSettings;
    const data = JSON.parse(raw) as Partial<Settings>;
    return {
      serverUrl: typeof data.serverUrl === "string" ? data.serverUrl : "",
      lang: data.lang === "en" ? "en" : "nb",
    };
  } catch {
    return defaultSettings;
  }
}

export async function saveSettings(settings: Settings): Promise<void> {
  await SecureStore.setItemAsync(KEY, JSON.stringify(settings));
}
