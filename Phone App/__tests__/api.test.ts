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
    expect(health.mats).toBe(5);
  });

  it("overview lists mats worst first with the real field names", async () => {
    const overview = await api.overview();
    expect(overview.mats.map((m) => m.risk)).toEqual(["offline", "high", "medium", "low", "none"]);
    expect(overview.open_alerts).toBe(2);
    expect(typeof overview.time).toBe("number");
  });

  it("mat detail has a snapshot, an offline mat has no grid", async () => {
    const high = await api.mat("sm-101");
    expect(high.snapshot.grid).toHaveLength(16);
    const offline = await api.mat("sm-104");
    expect(offline.snapshot.grid).toBeNull();
  });

  it("unknown mat is a 404 ApiError with the server text", async () => {
    await expect(api.mat("nope")).rejects.toMatchObject({ status: 404, message: "unknown mat" });
  });

  it("alerts use kind high/offline and no room field", async () => {
    const { alerts } = await api.alerts();
    expect(alerts.map((a) => a.kind).sort()).toEqual(["high", "offline"]);
    expect(alerts[0]).not.toHaveProperty("room");
  });

  it("acknowledge needs the right PIN", async () => {
    await expect(api.handleAlert("a1", "ack", "0000")).rejects.toMatchObject({ status: 403 });
    const alert = await api.handleAlert("a1", "ack", PIN);
    expect(alert.state).toBe("acknowledged");
    expect(alert.user).toBe("Test Nurse");
  });

  it("five wrong PINs lock the user out (429)", async () => {
    for (let i = 0; i < 5; i++) await api.handleAlert("a1", "ack", "9999").catch(() => undefined);
    await expect(api.handleAlert("a1", "ack", PIN)).rejects.toMatchObject({ status: 429 });
  });

  it("an unreachable server is status 0", async () => {
    const dead = createApi("http://127.0.0.1:1", 1000, nodeFetch);
    const error = await dead.health().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
  });
});
