import type { Risk, TimelineSegment } from "./types";

export interface Bar {
  x: number;
  w: number;
  risk: Risk;
  posture: TimelineSegment["posture"];
}

/** Bars for the last `hours` hours across `width` px. Gaps stay empty (= no data); segments are clipped to the window. */
export function layoutTimeline(segments: TimelineSegment[], now: number, hours: number, width: number): Bar[] {
  const start = now - hours * 3600;
  const scale = width / (hours * 3600);
  const bars: Bar[] = [];
  for (const s of segments) {
    const from = Math.max(s.t_start, start);
    const to = Math.min(s.t_end, now);
    if (to <= from) continue;
    bars.push({ x: (from - start) * scale, w: Math.max(2, (to - from) * scale), risk: s.risk, posture: s.posture });
  }
  return bars;
}

/** x position of a marker, or null when it is outside the window */
export function markerX(t: number, now: number, hours: number, width: number): number | null {
  const start = now - hours * 3600;
  return t < start || t > now ? null : ((t - start) / (hours * 3600)) * width;
}
