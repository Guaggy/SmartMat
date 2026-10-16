import type { Snapshot, Theme } from "./types";

export type Stops = Theme["heatmap_stops"];

// Fallback copy of HEATMAP_STOPS in Raspberry Pi/branding.py; the app prefers the ramp from GET /api/theme.
export const HEATMAP_STOPS: Stops = [
  [0.0, [207, 230, 222]], [0.25, [126, 189, 168]], [0.5, [233, 196, 106]],
  [0.75, [224, 123, 57]], [0.9, [179, 38, 30]], [1.0, [107, 15, 26]],
];

/** Colour for t in 0..1 (clamped), linear between the stops */
export function rampColor(t: number, stops: Stops = HEATMAP_STOPS): string {
  const x = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0));
  let i = 0;
  while (i < stops.length - 2 && x > stops[i + 1][0]) i++;
  const [t0, c0] = stops[i];
  const [t1, c1] = stops[i + 1];
  const f = t1 === t0 ? 0 : Math.min(1, Math.max(0, (x - t0) / (t1 - t0)));
  const [r, g, b] = c0.map((v, k) => Math.round(v + (c1[k] - v) * f));
  return `rgb(${r},${g},${b})`;
}

/** Cell colour: null is a dead cell (drawn as 0); values under 2 % of full scale fade into the background */
export function cellColor(value: number | null, scaleMax: number, stops: Stops, background: string): string {
  const t = scaleMax > 0 ? (value ?? 0) / scaleMax : 0;
  return t < 0.02 ? background : rampColor(t, stops);
}

/** Highest value in the grid, or null when there is no grid or nobody is on the mat */
export function peakValue(snapshot: Snapshot): number | null {
  if (!snapshot.grid || snapshot.occupied === false) return null;
  let peak: number | null = null;
  for (const row of snapshot.grid) for (const v of row) if (v !== null && (peak === null || v > peak)) peak = v;
  return peak;
}
