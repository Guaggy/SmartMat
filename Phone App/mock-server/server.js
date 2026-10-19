// Fake SmartMat server for developing the app without the real server or any hardware.
// Mimics Raspberry Pi/server/app.py as on main (see Raspberry Pi/design/api-contract.md), including error texts.
//   node mock-server/server.js            (PORT=8000, PIN 1234, user "Test Nurse")
// Extra controls: POST /__mock/raise {chip_id, kind}, POST /__mock/reset
const http = require("node:http");

const PIN = "1234";
const USER = "Test Nurse";
const SCALE_MAX = 50;
const ROWS = 16;
const COLS = 15;
const STALE_AFTER_S = 5;
const HEATMAP_STOPS = [
  [0.0, [207, 230, 222]], [0.25, [126, 189, 168]], [0.5, [233, 196, 106]],
  [0.75, [224, 123, 57]], [0.9, [179, 38, 30]], [1.0, [107, 15, 26]],
];

// frame: false = never sent a frame (snapshot null). offline + frame = offline with its last picture.
const MATS = [
  { id: "sm-101", name: "Stol 1", room: "101", seat: "A", unit: "Avd. A", risk: "high", posture: "right", tip: 1500, relief: 5400, peak: 46, frame: true },
  { id: "sm-102", name: "Stol 2", room: "102", seat: "A", unit: "Avd. A", risk: "medium", posture: "left", tip: 700, relief: 2400, peak: 34, frame: true },
  { id: "sm-103", name: "Stol 3", room: "103", seat: "B", unit: "Avd. B", risk: "low", posture: "centred", tip: 240, relief: 600, peak: 18, frame: true },
  { id: "sm-104", name: "Stol 4", room: "104", seat: "A", unit: "Avd. B", risk: "offline", posture: "none", tip: null, relief: null, peak: 0, frame: false },
  { id: "sm-105", name: "Stol 5", room: "105", seat: "A", unit: "Avd. B", risk: "none", posture: "none", tip: 173, relief: null, peak: 0, frame: true },
  { id: "sm-106", name: "Stol 6", room: "106", seat: "A", unit: "Avd. B", risk: "offline", posture: "none", tip: null, relief: null, peak: 30, frame: true },
];
const RISK_ORDER = ["offline", "high", "medium", "low", "none"];

function createMockServer(clock = () => Date.now() / 1000) {
  const t0 = clock();
  let alerts, events, wrongPins, lockedUntil, devices;

  function reset() {
    const now = clock();
    alerts = [
      alert("a1", "sm-101", "high_risk", now - 120),
      alert("a2", "sm-104", "offline", now - 900),
      Object.assign(alert("a0", "sm-103", "high_risk", now - 4000), { state: "acknowledged", by: "Kari", t_handled: now - 3800, t_cleared: now - 3000 }),
    ];
    events = [
      { id: 3, t: now - 3800, chip_id: "sm-103", kind: "alert acknowledged", user: "Kari", detail: { alert: "a0", kind: "high_risk" } },
      { id: 2, t: now - 900, chip_id: "sm-104", kind: "alert raised", user: null, detail: { alert: "a2", kind: "offline" } },
      { id: 1, t: now - 120, chip_id: "sm-101", kind: "alert raised", user: null, detail: { alert: "a1", kind: "high_risk" } },
    ];
    wrongPins = 0;
    lockedUntil = 0;
    devices = {};
  }
  function alert(id, chipId, kind, t) {
    return { id, chip_id: chipId, kind, t_raised: t, since: t - 30, t_cleared: null, state: "open", by: null, t_handled: null };
  }
  const mat = (id) => MATS.find((m) => m.id === id);
  const isOnline = (m) => m.risk !== "offline";

  function grid(m, now) {
    if (m.peak === 0) return Array.from({ length: ROWS }, () => Array(COLS).fill(0));
    const drift = isOnline(m) ? Math.sin((now - t0) / 8) * 0.6 : 0;
    const cy = 9 + drift, cx = m.posture === "left" ? 5 : m.posture === "right" ? 9.5 : 7;
    return Array.from({ length: ROWS }, (_, r) =>
      Array.from({ length: COLS }, (_, c) => {
        if (r === 0 && c === 0) return null; // a dead cell
        const d2 = ((r - cy) ** 2 + (c - cx) ** 2) / 14;
        return Math.round(Math.max(0, m.peak * Math.exp(-d2) + (r > 3 ? 2 : 0)) * 100) / 100;
      }));
  }
  function detail(m, now) {
    if (!m.frame) return null;
    const g = grid(m, now);
    const hot = [];
    g.forEach((row, r) => row.forEach((v, c) => { if (v !== null && v > 0.75 * m.peak && m.peak > 30) hot.push([r, c]); }));
    return {
      unit: "kPa", scale_max: SCALE_MAX, grid: g, occupied: isOnline(m) ? m.peak > 0 : null,
      hotspots: hot.length ? [{ id: 1, peak_kpa: m.peak, cells: hot, active_s: 120, persistent: m.risk === "high" }] : [],
      peak_kpa: m.peak > 0 ? m.peak : null,
      indices: m.peak > 0 ? [{ name: "Peak pressure (kPa)", layer: "pressure", value: m.peak, threshold: 45, near: 36,
        state: m.peak >= 45 ? "over" : m.peak >= 36 ? "near" : "ok" }] : [],
    };
  }
  function row(m, now) {
    const online = isOnline(m);
    return {
      id: m.id, name: m.name, room: m.room, seat: m.seat, unit: m.unit, demo: false,
      online, risk: m.risk, posture: online ? m.posture : "none",
      time_in_position_s: online && m.tip !== null ? m.tip + (now - t0) : null,
      since_relief_s: online ? m.relief : null, saturated_cells: m.risk === "high" ? 2 : 0, saturated: m.risk === "high",
      open_alerts: alerts.filter((a) => a.chip_id === m.id && a.state === "open").length,
    };
  }
  function segments(m, since, now) {
    if (!m.frame) return [];
    if (!isOnline(m)) return [{ t_start: now - 3600, t_end: now - 1800, posture: "centred", risk: "low" }];
    return [
      { t_start: now - 3600, t_end: now - 2400, posture: "centred", risk: "low" },
      { t_start: now - 2400, t_end: now - 1200, posture: m.posture, risk: m.risk === "low" ? "low" : "medium" },
      { t_start: now - 1200, t_end: now, posture: m.posture, risk: m.risk },
    ].filter((s) => s.t_end >= since);
  }
  const withName = (a) => Object.assign({}, a, { name: mat(a.chip_id).name, room: mat(a.chip_id).room });
  const recent = () => alerts.slice().sort((a, b) => b.t_raised - a.t_raised);

  function route(req, url, body, now) {
    const path = url.pathname;
    let m;
    if (req.method === "GET") {
      if (path === "/api/health") return [200, { ok: true, time: now, mats: MATS.length, version: "0.1.0", needs_admin: false }];
      if (path === "/api/theme") return [200, { light: {}, dark: {}, heatmap_stops: HEATMAP_STOPS }];
      if (path === "/api/overview") {
        const rows = MATS.map((x) => row(x, now));
        rows.sort((a, b) => RISK_ORDER.indexOf(a.risk) - RISK_ORDER.indexOf(b.risk) || (b.time_in_position_s || 0) - (a.time_in_position_s || 0) || (a.id < b.id ? -1 : 1));
        return [200, { mats: rows, open_alerts: alerts.filter((a) => a.state === "open").length, server_time: now }];
      }
      if (path === "/api/alerts") return [200, { alerts: recent().map(withName) }];
      if ((m = path.match(/^\/api\/mats\/([^/]+)(\/timeline|\/log)?$/))) {
        const found = mat(decodeURIComponent(m[1]));
        if (!found) return [404, { error: "Unknown mat" }];
        if (m[2] === "/log") return [200, { id: found.id, events: events.filter((e) => e.chip_id === found.id) }];
        if (m[2] === "/timeline") {
          const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || 1), 0), 168);
          const since = now - hours * 3600;
          return [200, { segments: segments(found, since, now),
            markers: events.filter((e) => e.chip_id === found.id && e.t >= since && e.kind.startsWith("alert ack")).map((e) => ({ t: e.t, kind: "handled", user: e.user })) }];
        }
        const age = found.frame ? (isOnline(found) ? 0.4 : 90 + (now - t0)) : null;
        return [200, Object.assign(row(found, now), { snapshot: detail(found, now), age_s: age, stale: !isOnline(found) })];
      }
      if (path === "/api/users") return [200, { users: [{ id: 1, name: USER, role: "admin", active: true }], needs_admin: false }];
    }
    if (req.method === "POST" && (m = path.match(/^\/api\/alerts\/([^/]+)\/([^/]+)$/))) {
      if (m[2] !== "ack" && m[2] !== "ignore") return [404, { error: "Unknown action" }];
      if (!body || typeof body !== "object") return [400, { error: "Send a JSON object" }];
      if (!body.pin) return [401, { error: "PIN required" }];
      if (now < lockedUntil) return [429, { error: "Too many wrong PINs, try again later" }];
      if (String(body.pin) !== PIN) {
        if (++wrongPins >= 5) { lockedUntil = now + 30; wrongPins = 0; }
        return [403, { error: "Wrong PIN" }];
      }
      wrongPins = 0;
      const a = alerts.find((x) => x.id === m[1]);
      if (!a || a.t_cleared !== null) return [409, { error: "This alert is no longer open" }];
      if (a.state !== "open") return [409, { error: "Alert already handled by " + a.by }];
      Object.assign(a, { state: m[2] === "ack" ? "acknowledged" : "ignored", by: USER, t_handled: now });
      events.unshift({ id: events.length + 1, t: now, chip_id: a.chip_id, kind: m[2] === "ack" ? "alert acknowledged" : "alert ignored", user: USER, detail: { alert: a.id, kind: a.kind } });
      return [200, { ok: true, user: USER, alert: Object.assign({}, a) }];
    }
    // Phones for push (needs the patch in server-patch/ on the real server). Register needs a PIN, the rest is by token.
    if (req.method === "POST" && path === "/api/devices") {
      if (!body || typeof body !== "object") return [400, { error: "Send a JSON object" }];
      if (!body.pin) return [401, { error: "PIN required" }];
      if (now < lockedUntil) return [429, { error: "Too many wrong PINs, try again later" }];
      if (String(body.pin) !== PIN) {
        if (++wrongPins >= 5) { lockedUntil = now + 30; wrongPins = 0; }
        return [403, { error: "Wrong PIN" }];
      }
      wrongPins = 0;
      if (body.platform !== "android" && body.platform !== "ios") return [400, { error: "Platform must be android or ios" }];
      if (!/^Expo(nent)?PushToken\[[A-Za-z0-9_-]{1,200}\]$/.test(String(body.expo_push_token))) return [400, { error: "That is not an Expo push token" }];
      const { pin, expo_push_token, ...rest } = body;
      devices[expo_push_token] = rest;
      return [201, { ok: true, user: USER }];
    }
    if ((m = path.match(/^\/api\/devices\/(.+)$/)) && (req.method === "PUT" || req.method === "DELETE")) {
      const token = decodeURIComponent(m[1]);
      if (!devices[token]) return [404, { error: "Unknown device" }];
      if (req.method === "DELETE") { delete devices[token]; return [200, { ok: true }]; }
      Object.assign(devices[token], body || {});
      return [200, { ok: true }];
    }
    if (req.method === "GET" && path === "/__mock/devices") return [200, devices];
    if (req.method === "POST" && path === "/__mock/reset") { reset(); return [200, { ok: true }]; }
    if (req.method === "POST" && path === "/__mock/raise") {
      if (!body || !mat(body.chip_id)) return [404, { error: "Unknown mat" }];
      const a = alert(Math.random().toString(16).slice(2, 14), body.chip_id, body.kind === "offline" ? "offline" : "high_risk", now);
      alerts.push(a);
      return [200, a];
    }
    return [404, { error: "Not found" }];
  }

  reset();
  const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "GET,POST,DELETE,PUT,OPTIONS" };
  return http.createServer((req, res) => {
    if (req.method === "OPTIONS") { res.writeHead(204, cors); return res.end(); } // lets a browser/web build call the mock
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      let body = null;
      try { body = JSON.parse(Buffer.concat(chunks).toString() || "null"); } catch (e) { body = null; }
      const [status, payload] = route(req, new URL(req.url, "http://x"), body, clock());
      res.writeHead(status, Object.assign({ "Content-Type": "application/json", "Cache-Control": "no-store" }, cors));
      res.end(JSON.stringify(payload));
    });
  });
}

module.exports = { createMockServer, PIN, USER };

if (require.main === module) {
  const port = Number(process.env.PORT || 8000);
  createMockServer().listen(port, "0.0.0.0", () => console.log(`SmartMat mock server on http://0.0.0.0:${port} (PIN ${PIN})`));
}
