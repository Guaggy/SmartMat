import { bannerAlert, diffAlerts, initialWatch, mayMakeNoise } from "../src/alertWatch";
import { connectionErrorKey } from "../src/errors";
import { ApiError, normalizeUrl } from "../src/api";
import { isExpoGoEnv } from "../src/env";
import { shouldGoToSetup } from "../src/firstRun";
import type { Alert } from "../src/types";

const alert = (id: string, extra: Partial<Alert> = {}): Alert => ({
  id, chip_id: "sm-1", kind: "high_risk", t_raised: 100, since: 70, t_cleared: null, state: "open", by: null, t_handled: null, ...extra,
});

describe("alert watching", () => {
  it("the first poll only records what is open: no notification for old news", () => {
    const { fresh, next } = diffAlerts([alert("a"), alert("b")], initialWatch);
    expect(fresh).toEqual([]);
    expect(next.primed).toBe(true);
  });

  it("announces a new open alert once, oldest first, and never again", () => {
    let state = diffAlerts([alert("a")], initialWatch).next;
    const second = diffAlerts([alert("a"), alert("c", { t_raised: 300 }), alert("b", { t_raised: 200 })], state);
    expect(second.fresh.map((a) => a.id)).toEqual(["b", "c"]);
    state = second.next;
    expect(diffAlerts([alert("a"), alert("b"), alert("c")], state).fresh).toEqual([]);
  });

  it("a server restart or a failed poll in between does not re-notify", () => {
    let state = diffAlerts([alert("a")], initialWatch).next;
    state = diffAlerts([alert("n", { t_raised: 500 })], state).next; // n announced; a vanished for a moment
    expect(diffAlerts([alert("a"), alert("n")], state).fresh.map((a) => a.id)).toEqual([]);
  });

  it("ignores handled and cleared alerts", () => {
    const primed = diffAlerts([], initialWatch).next;
    const list = [alert("x", { state: "acknowledged" }), alert("y", { t_cleared: 5 }), alert("z", { state: "ignored" })];
    expect(diffAlerts(list, primed).fresh).toEqual([]);
  });

  it("keeps the remembered ids bounded", () => {
    let state = diffAlerts([], initialWatch).next;
    for (let i = 0; i < 400; i++) state = diffAlerts([alert(`id${i}`)], state).next;
    expect(state.seen.length).toBeLessThanOrEqual(300);
  });

  it("quiet hours hold back noise only while on and inside the window", () => {
    const quiet = { enabled: true, from: "22:00", to: "07:00" };
    expect(mayMakeNoise(quiet, new Date(2026, 0, 1, 23, 0))).toBe(false);
    expect(mayMakeNoise(quiet, new Date(2026, 0, 1, 12, 0))).toBe(true);
    expect(mayMakeNoise({ ...quiet, enabled: false }, new Date(2026, 0, 1, 23, 0))).toBe(true);
  });

  it("the banner shows the newest open alert that is not hidden, and counts the rest", () => {
    const list = [alert("a", { t_raised: 1 }), alert("b", { t_raised: 3 }), alert("c", { t_raised: 2 }), alert("d", { state: "ignored" })];
    expect(bannerAlert(list, new Set())).toMatchObject({ alert: { id: "b" }, more: 2 });
    expect(bannerAlert(list, new Set(["b"]))).toMatchObject({ alert: { id: "c" }, more: 1 });
    expect(bannerAlert(list, new Set(["a", "b", "c"]))).toEqual({ alert: null, more: 0 });
  });
});

describe("server address", () => {
  it("accepts Tailscale addresses and MagicDNS names, adding http and the default port", () => {
    expect(normalizeUrl("100.101.102.103")).toBe("http://100.101.102.103:8000");
    expect(normalizeUrl("smartmat-pi")).toBe("http://smartmat-pi:8000");
    expect(normalizeUrl("pi.tail1234.ts.net:8000/")).toBe("http://pi.tail1234.ts.net:8000");
    expect(normalizeUrl("HTTP://100.64.0.2:9000/dashboard?x=1")).toBe("http://100.64.0.2:9000");
    expect(normalizeUrl("https://sm.example.com")).toBe("https://sm.example.com");
    expect(normalizeUrl("two words")).toBe("");
    expect(normalizeUrl("")).toBe("");
  });

  it("picks a clear message for each way a connection fails", () => {
    expect(connectionErrorKey(new ApiError(0, "x", "timeout"), "http://a:8000")).toBe("errTimeout");
    expect(connectionErrorKey(new ApiError(0, "x", "network"), "http://a:8000")).toBe("errNetwork");
    expect(connectionErrorKey(new ApiError(0, "x", "network"), "https://a")).toBe("errNetworkHttps");
    expect(connectionErrorKey(new ApiError(200, "x", "notSmartMat"), "http://a:80")).toBe("errNotSmartMat");
    expect(connectionErrorKey(new ApiError(404, "x"), "http://a:80")).toBe("errNotSmartMat");
    expect(connectionErrorKey(new ApiError(500, "x"), "http://a:8000")).toBe("errHttp");
  });
});

describe("Expo Go and first run", () => {
  it("recognises Expo Go by its execution environment", () => {
    expect(isExpoGoEnv("storeClient")).toBe(true);
    expect(isExpoGoEnv("bare")).toBe(false);
    expect(isExpoGoEnv("standalone")).toBe(false);
    expect(isExpoGoEnv(undefined, "expo")).toBe(true);
  });

  it("goes to Settings once, only when loaded and without a server", () => {
    expect(shouldGoToSetup(false, "", false)).toBe(false); // settings still loading
    expect(shouldGoToSetup(true, "", false)).toBe(true);
    expect(shouldGoToSetup(true, "", true)).toBe(false); // already sent: no loop
    expect(shouldGoToSetup(true, "http://a:8000", false)).toBe(false);
  });
});
