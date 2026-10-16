// All UI text. Norwegian (nb) is the default and the source of the key list; English must have the same keys.
// Wording follows Raspberry Pi/server/static/app.js so the app and the web dashboard read the same.
// Framing rule: "pressure", "risk level (indicative)". Never diagnosis, ulcer probability or a validated score.

const nb = {
  appName: "SmartMat",
  overview: "Oversikt",
  alerts: "Varsler",
  settings: "Innstillinger",
  placeholder: "Appen er under bygging.",
  disclaimer:
    "Ingeniørverktøy, ikke medisinsk utstyr. Stilling og risiko er heuristikker (veiledende). Bruk sammen med vanlig klinisk vurdering.",
};

const en: Record<keyof typeof nb, string> = {
  appName: "SmartMat",
  overview: "Overview",
  alerts: "Alerts",
  settings: "Settings",
  placeholder: "The app is under construction.",
  disclaimer:
    "Engineering aid, not a medical device. Posture and risk are heuristics (indicative). Use alongside normal clinical assessment.",
};

export type Lang = "nb" | "en";
export type StringKey = keyof typeof nb;
const dictionaries: Record<Lang, Record<StringKey, string>> = { nb, en };

export const defaultLang: Lang = "nb";

export function t(key: StringKey, lang: Lang = defaultLang): string {
  return dictionaries[lang][key] ?? nb[key];
}
