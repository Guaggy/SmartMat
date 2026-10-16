import * as SecureStore from "expo-secure-store";

import { defaultLang, type Lang } from "./strings";

export interface QuietHours {
  enabled: boolean;
  from: string; // "HH:MM"
  to: string;
}

export interface Settings {
  serverUrl: string;
  lang: Lang;
  quiet: QuietHours;
}

const KEY = "smartmat.settings";
export const defaultQuiet: QuietHours = { enabled: false, from: "22:00", to: "07:00" };
export const defaultSettings: Settings = { serverUrl: "", lang: defaultLang, quiet: defaultQuiet };

// Server address, language and quiet hours only. The PIN is never stored: it is asked for on every alert action.
export async function loadSettings(): Promise<Settings> {
  try {
    const raw = await SecureStore.getItemAsync(KEY);
    if (!raw) return defaultSettings;
    const data = JSON.parse(raw) as Partial<Settings>;
    return {
      serverUrl: typeof data.serverUrl === "string" ? data.serverUrl : "",
      lang: data.lang === "en" ? "en" : "nb",
      quiet: { ...defaultQuiet, ...(data.quiet ?? {}) },
    };
  } catch {
    return defaultSettings;
  }
}

export async function saveSettings(settings: Settings): Promise<void> {
  try {
    await SecureStore.setItemAsync(KEY, JSON.stringify(settings));
  } catch {
    // Store unavailable: the settings still apply for this session, they are just not remembered
  }
}
