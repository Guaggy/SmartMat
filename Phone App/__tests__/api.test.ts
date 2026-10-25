/** @jest-environment node */
import type { AddressInfo } from "node:net";
import http, { type Server } from "node:http";

import { ApiError, createApi, normalizeUrl } from "../src/api";

const { createMockServer, PIN } = require("../mock-server/server.js");

// jest-expo replaces the global fetch with a stub, so the tests talk to the mock server through node:http.
const nodeFetch = ((url: string, init: { method?: string; body?: string; headers?: Record<string, string> } = {}) =>
  new Promise((resolve, reject) => {
    const req = http.request(url, { method: init.method, headers: init.headers }, (res) => {
      const chunks: Buffer[] = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => {
        const text = Buffer.concat(chunks).toString();
        const status = res.statusCode ?? 0;
        resolve({ ok: status >= 200 && status < 300, status, json: async () => JSON.parse(text) });
      });
    });
    req.on("error", reject);
    req.end(init.body);
  })) as unknown as typeof fetch;

let server: Server;
let api: ReturnType<typeof createApi>;
let base: string;

beforeAll(async () => {
  server = createMockServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  api = createApi(base, 3000, nodeFetch);
});
afterAll(() => new Promise<void>((resolve) => server.close(() => resolve())));
beforeEach(async () => {
  await nodeFetch(`${base}/__mock/reset`, { method: "POST" });
});

describe("normalizeUrl", () => {
  it("adds http and strips trailing slashes", () => {
    expect(normalizeUrl(" 192.168.1.50:8000/ ")).toBe("http://192.168.1.50:8000");
    expect(normalizeUrl("https://sm.example.com//")).toBe("https://sm.example.com");
    expect(normalizeUrl("   ")).toBe("");
  });
});

describe("api against the mock server", () => {
  it("health works as a connection test", async () => {
    const health = await api.health();
    expect(health.ok).toBe(true);
    expect(health.mats).toBe(6);
    expect(health.needs_admin).toBe(false);
  });

  it("overview lists mats worst first with room/seat/unit as strings", async () => {
    const overview = await api.overview();
    expect(overview.mats.map((m) => m.risk)).toEqual(["offline", "offline", "high", "medium", "low", "none"]);
    expect(overview.open_alerts).toBe(2);
    expect(typeof overview.server_time).toBe("number");
    expect(overview.mats.every((m) => typeof m.room === "string")).toBe(true);
  });

  it("mat detail: picture for a live mat, last picture when offline, null before the first frame", async () => {
    const high = await api.mat("sm-101");
    expect(high.snapshot?.grid).toHaveLength(16);
    expect(high.snapshot?.peak_kpa).toBe(46);
    expect(high.stale).toBe(false);
    const offline = await api.mat("sm-106");
    expect(offline.stale).toBe(true);
    expect(offline.snapshot?.grid).not.toBeNull();
    expect(offline.age_s).toBeGreaterThan(0);
    const never = await api.mat("sm-104");
    expect(never.snapshot).toBeNull();
    expect(never.age_s).toBeNull();
  });

  it("timeline has segments and handled markers", async () => {
    const tl = await api.timeline("sm-103", 2);
    expect(tl.segments.length).toBeGreaterThan(0);
    expect(tl.markers).toEqual([expect.objectContaining({ kind: "handled", user: "Kari" })]);
  });

  it("unknown mat is a 404 ApiError with the server text", async () => {
    await expect(api.mat("nope")).rejects.toMatchObject({ status: 404, message: "Unknown mat" });
  });

  it("alerts: high_risk/offline kinds, room, and handled history", async () => {
    const { alerts } = await api.alerts();
    expect(alerts.map((a) => a.kind).sort()).toEqual(["high_risk", "high_risk", "offline"]);
    expect(alerts.find((a) => a.id === "a1")).toMatchObject({ name: "Stol 1", room: "101", state: "open", by: null });
    expect(alerts.find((a) => a.id === "a0")).toMatchObject({ state: "acknowledged", by: "Kari" });
  });

  it("acknowledge needs the right PIN and returns who handled it", async () => {
    await expect(api.handleAlert("a1", "ack", "0000")).rejects.toMatchObject({ status: 403, message: "Wrong PIN" });
    const result = await api.handleAlert("a1", "ack", PIN);
    expect(result.ok).toBe(true);
    expect(result.user).toBe("Test Nurse");
    expect(result.alert.state).toBe("acknowledged");
  });

  it("an alert that is already handled or cleared is a 409", async () => {
    await api.handleAlert("a1", "ack", PIN);
    await expect(api.handleAlert("a1", "ignore", PIN)).rejects.toMatchObject({ status: 409 });
    await expect(api.handleAlert("a0", "ack", PIN)).rejects.toMatchObject({ status: 409 });
  });

  it("five wrong PINs lock the user out (429)", async () => {
    for (let i = 0; i < 5; i++) await api.handleAlert("a1", "ack", "9999").catch(() => undefined);
    await expect(api.handleAlert("a1", "ack", PIN)).rejects.toMatchObject({ status: 429 });
  });

  it("registering a phone for push needs a PIN, then it can be updated and removed by token", async () => {
    const token = "ExponentPushToken[abc_DEF-123]";
    const settings = { name: "Pixel", lang: "nb" as const, tz: "Europe/Oslo", quiet_from: "22:00", quiet_to: "07:00" };
    await expect(api.registerDevice(token, "android", "0000", settings)).rejects.toMatchObject({ status: 403 });
    await expect(api.registerDevice("nope", "android", PIN, settings)).rejects.toMatchObject({ status: 400 });
    expect(await api.registerDevice(token, "android", PIN, settings)).toEqual({ ok: true, user: "Test Nurse" });
    expect(await api.updateDevice(token, { quiet_from: null, quiet_to: null })).toEqual({ ok: true });
    const stored = await (await nodeFetch(`${base}/__mock/devices`)).json();
    expect(stored[token]).toMatchObject({ platform: "android", lang: "nb", tz: "Europe/Oslo", quiet_from: null });
    expect(stored[token]).not.toHaveProperty("pin"); // the PIN is never kept
    expect(await api.unregisterDevice(token)).toEqual({ ok: true });
    await expect(api.unregisterDevice(token)).rejects.toMatchObject({ status: 404 });
    await expect(api.updateDevice(token, { lang: "en" })).rejects.toMatchObject({ status: 404 });
  });

  it("an unreachable server is status 0, kind network", async () => {
    const dead = createApi("http://127.0.0.1:1", 1000, nodeFetch);
    const error = await dead.health().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).kind).toBe("network");
  });

  it("a server that answers but is not SmartMat is notSmartMat", async () => {
    const notSmartMat = (async () => ({ ok: true, status: 200, json: async () => ({ hello: "world" }) })) as unknown as typeof fetch;
    const error = await createApi("http://x:80", 1000, notSmartMat).health().catch((e) => e);
    expect((error as ApiError).kind).toBe("notSmartMat");
  });

  it("raise and clear from a script: a raised alert is open, clearing makes it vanish, rows carry since_movement_s", async () => {
    const post = (path: string, body: unknown) =>
      nodeFetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    await post("/__mock/raise", { chip_id: "sm-102", kind: "high" });
    let alerts = (await api.alerts()).alerts.filter((a) => a.chip_id === "sm-102");
    expect(alerts.map((a) => [a.kind, a.state])).toEqual([["high_risk", "open"]]);
    const cleared = await (await post("/__mock/clear", { chip_id: "sm-102" })).json();
    expect(cleared.cleared).toHaveLength(1);
    alerts = (await api.alerts()).alerts.filter((a) => a.chip_id === "sm-102");
    expect(alerts).toEqual([]);
    const rows = (await api.overview()).mats;
    expect(rows.find((m) => m.id === "sm-102")?.since_movement_s).toEqual(expect.any(Number));
    expect(rows.find((m) => m.id === "sm-104")?.since_movement_s).toBeNull(); // offline
  });

  it("the mock logs method, path and status of each request", async () => {
    const lines: string[] = [];
    const logged = createMockServer(undefined, (line: string) => lines.push(line));
    await new Promise<void>((resolve) => logged.listen(0, "127.0.0.1", resolve));
    const url = `http://127.0.0.1:${(logged.address() as AddressInfo).port}`;
    await createApi(url, 3000, nodeFetch).overview();
    await createApi(url, 3000, nodeFetch).mat("nope").catch(() => undefined);
    await new Promise<void>((resolve) => logged.close(() => resolve()));
    expect(lines).toEqual(["GET /api/overview -> 200", "GET /api/mats/nope -> 404"]);
  });
});
