// JSON shapes of the SmartMat server, copied from Raspberry Pi/server/app.py, alerts.py, engine.py and store.py.
// HANDOFF.md and tools/mock_api.py differ in places; this file follows the real server. Fix shapes here only.
// Times are unix seconds, durations are seconds.

export type Risk = "high" | "medium" | "low" | "none" | "offline";
export type Posture = "left" | "right" | "forward" | "centred" | "none";

export interface Health {
  ok: boolean;
  time: number;
  mats: number;
  version: string;
}

export interface MatInfo {
  id: string;
  name: string;
  room: string | null;
  seat: string | null;
  unit: string | null;
  demo: boolean;
}

export interface OverviewRow extends MatInfo {
  online: boolean;
  risk: Risk;
  posture: Posture;
  time_in_position_s: number | null;
  saturated_cells: number;
  saturated: boolean;
  since_relief_s: number | null;
  open_alerts: number;
}

export interface Overview {
  time: number;
  mats: OverviewRow[]; // worst first
  open_alerts: number;
}

export interface Hotspot {
  id: number;
  peak_kpa: number;
  cells: [number, number][]; // [row, col]
  active_s: number;
  persistent: boolean;
}

export interface Index {
  name: string;
  layer: string;
  value: number | null;
  threshold: number;
  near: number;
  state: "ok" | "near" | "over";
}

// Offline mats and mats that never sent a frame only have the first block of fields (grid is null).
export interface Snapshot {
  online: boolean;
  risk: Risk;
  posture: Posture;
  time_in_position_s: number | null;
  saturated_cells: number;
  since_relief_s: number | null;
  occupied: boolean | null;
  grid: (number | null)[][] | null; // row 0 = back of the seat, last row = front
  unit?: "kPa" | "relative";
  scale_max?: number;
  hotspots?: Hotspot[];
  indices?: Index[];
  shape?: [number, number];
  profile_version?: number;
}

export interface TimelineSegment {
  t_start: number;
  t_end: number;
  posture: Posture;
  risk: Risk;
}

export interface MatDetail extends MatInfo {
  snapshot: Snapshot;
  timeline: TimelineSegment[]; // last hour
  alerts: Alert[];
}

export interface MatTimeline {
  id: string;
  timeline: TimelineSegment[];
}

export type AlertKind = "high" | "offline";
export type AlertState = "open" | "acknowledged" | "ignored";

// The server only lists alerts whose condition is still active (handled ones stay until it clears).
export interface Alert {
  id: string;
  chip_id: string;
  kind: AlertKind;
  t_raised: number;
  since: number;
  t_cleared: number | null;
  state: AlertState;
  user: string | null;
  t_handled: number | null;
  name?: string; // added by GET /api/alerts only
}

export interface LogEvent {
  id: number;
  t: number;
  chip_id: string | null;
  kind: string;
  user: string | null;
  detail: Record<string, unknown> | null;
}

export interface Theme {
  palette_light: Record<string, string>;
  palette_dark: Record<string, string>;
  heatmap_stops: [number, [number, number, number]][];
}

export type AlertAction = "ack" | "ignore";
