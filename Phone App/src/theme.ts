import type { Risk } from "./types";

// Dark palette from Raspberry Pi/branding.py (PALETTE_DARK); the app is dark-only for now.
export const colors = {
  bg: "#0A101D",
  panel: "#111A2D",
  line: "#243049",
  ink: "#E6EBF2",
  muted: "#93A0B5",
  accent: "#74B89C",
  onAccent: "#10182B",
  ok: "#6FC49C",
  warn: "#E6B45A",
  bad: "#F08A80",
  idle: "#9AA6BA",
};

// Colour is never the only signal: every risk also has its text label (see RiskPill).
export const riskColor: Record<Risk, string> = {
  high: colors.bad,
  medium: colors.warn,
  low: colors.ok,
  none: colors.idle,
  offline: colors.idle,
};

export function asRisk(value: string): Risk {
  // An unknown value is drawn as "none" (grey), never as green.
  return value === "high" || value === "medium" || value === "low" || value === "offline" ? value : "none";
}
