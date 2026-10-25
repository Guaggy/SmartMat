// JSON shapes of the SmartMat server: Raspberry Pi/server/app.py and Raspberry Pi/design/api-contract.md.
// Checked against main at af4f8c4. If the server changes, fix the shapes here only.
// Times are unix seconds, durations are seconds.

export type Risk = "high" | "medium" | "low" | "none" | "offline";
export type Posture = "left" | "right" | "forward" | "centred" | "none";

export interface Health {
  ok: boolean;
  time: number;
  mats: number;
  version: string;
  needs_admin: boolean; // true while the server has no users yet
}

export interface MatInfo {
  id: string;
  name: string;
  room: string; // "" when not set
  seat: string;
  unit: string;
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
  since_movement_s?: number | null; // seconds since the mat last registered movement; not in every server version yet
  open_alerts: number;
}

export interface Overview {
  mats: OverviewRow[]; // worst first
  open_alerts: number;
  server_time: number;
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

// The picture part of a mat. null when the mat has not sent a frame yet; an offline mat keeps its last picture.
export interface SnapshotDetail {
  unit: "kPa" | "relative";
  scale_max: number;
  grid: (number | null)[][] | null; // row 0 = back of the seat, last row = front
  occupied: boolean | null;
  hotspots: Hotspot[];
  peak_kpa: number | null; // null for a relative (uncalibrated) signal
  indices: Index[];
}

export interface TimelineSegment {
  t_start: number;
  t_end: number;
  posture: Posture;
  risk: Risk;
}

export interface TimelineMarker {
  t: number;
  kind: "handled";
  user: string | null;
}

export interface MatDetail extends OverviewRow {
  snapshot: SnapshotDetail | null;
  age_s: number | null; // seconds since the last frame, null before the first one
  stale: boolean;
}

export interface MatTimeline {
  segments: TimelineSegment[];
  markers: TimelineMarker[];
}

export type AlertKind = "high_risk" | "offline";
export type AlertState = "open" | "acknowledged" | "ignored";

// GET /api/alerts: alerts whose condition is still present plus the last 30 handled ones that have cleared.
export interface Alert {
  id: string;
  chip_id: string;
  kind: AlertKind;
  t_raised: number;
  since: number;
  t_cleared: number | null;
  state: AlertState;
  by: string | null; // user who acknowledged or ignored it
  t_handled: number | null;
  name?: string; // mat name and room are added by GET /api/alerts only
  room?: string;
}

export interface AlertResult {
  ok: boolean;
  user: string;
  alert: Alert;
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
  light: Record<string, string>;
  dark: Record<string, string>;
  heatmap_stops: [number, [number, number, number]][];
}

export type AlertAction = "ack" | "ignore";

// POST /api/devices (needs a PIN) and PUT /api/devices/<token> (no PIN; the push token is the secret)
export interface DeviceSettings {
  name?: string;
  lang?: "nb" | "en";
  tz?: string; // IANA zone, e.g. "Europe/Oslo"; the server applies the quiet window in this zone
  quiet_from?: string | null; // "HH:MM"
  quiet_to?: string | null;
}
