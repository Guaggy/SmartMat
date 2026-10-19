import { alertErrorKey } from "../src/errors";
import { ApiError } from "../src/api";
import { cellColor, HEATMAP_STOPS, peakValue, rampColor } from "../src/heatmap";
import { isQuiet, parseTime } from "../src/quietHours";
import { layoutTimeline, markerX } from "../src/timeline";
import type { SnapshotDetail } from "../src/types";

describe("heatmap", () => {
  it("hits the end stops and clamps", () => {
    expect(rampColor(0)).toBe("rgb(207,230,222)");
    expect(rampColor(1)).toBe("rgb(107,15,26)");
    expect(rampColor(-5)).toBe(rampColor(0));
    expect(rampColor(9)).toBe(rampColor(1));
    expect(rampColor(NaN)).toBe(rampColor(0));
  });
  it("interpolates between stops", () => {
    expect(rampColor(0.125)).toBe("rgb(167,210,195)"); // halfway between stop 0 and stop 0.25
    expect(rampColor(0.5, HEATMAP_STOPS)).toBe("rgb(233,196,106)");
  });
  it("fades near-zero and dead cells into the background", () => {
    expect(cellColor(null, 50, HEATMAP_STOPS, "bg")).toBe("bg");
    expect(cellColor(0.5, 50, HEATMAP_STOPS, "bg")).toBe("bg");
    expect(cellColor(25, 50, HEATMAP_STOPS, "bg")).toBe("rgb(233,196,106)");
  });
  it("finds the peak of a relative signal, ignoring dead cells and empty mats", () => {
    const base: Omit<SnapshotDetail, "grid" | "occupied"> = { unit: "relative", scale_max: 1, hotspots: [], peak_kpa: null, indices: [] };
    const grid = [[null, 3], [12.5, 4]];
    expect(peakValue({ ...base, occupied: true, grid })).toBe(12.5);
    expect(peakValue({ ...base, occupied: false, grid })).toBeNull();
    expect(peakValue({ ...base, occupied: true, grid: null })).toBeNull();
  });
});

describe("timeline layout", () => {
  const seg = (a: number, b: number) => ({ t_start: a, t_end: b, posture: "centred" as const, risk: "low" as const });
  it("places bars across the window and keeps gaps empty", () => {
    // now=3700, 1 h window starts at 100 s, 0.1 px per second
    const bars = layoutTimeline([seg(1000, 1900), seg(2800, 3700)], 3700, 1, 360);
    expect(bars.map((b) => [Math.round(b.x), Math.round(b.w)])).toEqual([[90, 90], [270, 90]]);
  });
  it("clips segments older than the window and drops empty ones", () => {
    const bars = layoutTimeline([seg(0, 100), seg(0, 4000)], 7200, 1, 360);
    expect(bars).toHaveLength(1);
    expect(bars[0].x).toBe(0);
  });
});

describe("timeline markers", () => {
  it("places a marker inside the window and drops others", () => {
    expect(markerX(3400, 3700, 1, 360)).toBeCloseTo(330, 5);
    expect(markerX(50, 3700, 1, 360)).toBeNull();
    expect(markerX(4000, 3700, 1, 360)).toBeNull();
  });
});

describe("quiet hours", () => {
  const at = (h: number, m = 0) => new Date(2026, 0, 1, h, m);
  it("parses HH:MM", () => {
    expect(parseTime("22:30")).toBe(1350);
    expect(parseTime("7:05")).toBe(425);
    expect(parseTime("24:00")).toBeNull();
    expect(parseTime("abc")).toBeNull();
  });
  it("handles a window that wraps past midnight", () => {
    expect(isQuiet(at(23), "22:00", "07:00")).toBe(true);
    expect(isQuiet(at(3), "22:00", "07:00")).toBe(true);
    expect(isQuiet(at(7), "22:00", "07:00")).toBe(false);
    expect(isQuiet(at(12), "22:00", "07:00")).toBe(false);
  });
  it("handles a same-day window and ignores bad input", () => {
    expect(isQuiet(at(13), "12:00", "14:00")).toBe(true);
    expect(isQuiet(at(14), "12:00", "14:00")).toBe(false);
    expect(isQuiet(at(3), "bad", "07:00")).toBe(false);
    expect(isQuiet(at(3), "07:00", "07:00")).toBe(false);
  });
});

describe("alert errors", () => {
  it("maps server statuses to texts", () => {
    expect(alertErrorKey(new ApiError(403, "x"))).toBe("errWrongPin");
    expect(alertErrorKey(new ApiError(429, "x"))).toBe("errLocked");
    expect(alertErrorKey(new ApiError(409, "x"))).toBe("errNotOpen");
    expect(alertErrorKey(new ApiError(404, "x"))).toBe("errNotOpen");
    expect(alertErrorKey(new ApiError(0, "x"))).toBe("netErr");
    expect(alertErrorKey(new Error("boom"))).toBe("netErr");
  });
});
