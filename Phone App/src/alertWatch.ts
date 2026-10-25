import { isQuiet } from "./quietHours";
import type { Alert } from "./types";

// Pure logic for in-app alerts: which alerts are new, and whether to make noise.

export interface WatchState {
  primed: boolean; // false until the first successful poll of this session
  seen: string[]; // alert ids already announced (or present when the app started)
}

export const initialWatch: WatchState = { primed: false, seen: [] };
const MAX_SEEN = 300;

export const isOpen = (a: Alert) => a.state === "open" && a.t_cleared === null;

/** New open alerts since the last poll. The first poll only records what is already open (a user opening the app sees
 *  those in the banner; no notification for old news). An id is announced once: a server restart, a failed poll or
 *  the same alert showing up again never re-notifies. */
export function diffAlerts(alerts: Alert[], state: WatchState): { fresh: Alert[]; next: WatchState } {
  const open = alerts.filter(isOpen);
  const known = new Set(state.seen);
  const fresh = state.primed ? open.filter((a) => !known.has(a.id)) : [];
  const added = open.filter((a) => !known.has(a.id)).map((a) => a.id);
  const seen = [...state.seen, ...added].slice(-MAX_SEEN);
  return { fresh: fresh.sort((a, b) => a.t_raised - b.t_raised), next: { primed: true, seen } };
}

/** Sound, vibration and local notification are held back during the user's quiet hours; the banner always shows */
export function mayMakeNoise(quiet: { enabled: boolean; from: string; to: string }, now: Date): boolean {
  return !(quiet.enabled && isQuiet(now, quiet.from, quiet.to));
}

/** The alert the banner shows: the newest open one that has not been hidden with "Later" */
export function bannerAlert(alerts: Alert[], hidden: ReadonlySet<string>): { alert: Alert | null; more: number } {
  const list = alerts.filter((a) => isOpen(a) && !hidden.has(a.id)).sort((a, b) => b.t_raised - a.t_raised);
  return { alert: list[0] ?? null, more: Math.max(0, list.length - 1) };
}
