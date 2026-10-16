// Fake SmartMat server for developing the app without the real server or any hardware.
// Mimics the JSON shapes of Raspberry Pi/server/app.py (not tools/mock_api.py, which differs from the real code).
//   node mock-server/server.js            (PORT=8000, PIN 1234, user "Test Nurse")
// Extra controls: POST /__mock/raise {chip_id, kind}, POST /__mock/reset
const http = require("node:http");

const PIN = "1234";
const USER = "Test Nurse";
const SCALE_MAX = 50;
const ROWS = 16;
const COLS = 15;
const HEATMAP_STOPS = [
  [0.0, [207, 230, 222]], [0.25, [126, 189, 168]], [0.5, [233, 196, 106]],
  [0.75, [224, 123, 57]], [0.9, [179, 38, 30]], [1.0, [107, 15, 26]],
];

const MATS = [
  { id: "sm-101", name: "Stol 1", room: "101", seat: "A", unit: "Avd. A", risk: "high", posture: "right", tip: 1500, relief: 5400, peak: 46 },
  { id: "sm-102", name: "Stol 2", room: "102", seat: "A", unit: "Avd. A", risk: "medium", posture: "left", tip: 700, relief: 2400, peak: 34 },
  { id: "sm-103", name: "Stol 3", room: "103", seat: "B", unit: "Avd. B", risk: "low", posture: "centred", tip: 240, relief: 600, peak: 18 },
  { id: "sm-104", name: "Stol 4", room: "104", seat: "A", unit: "Avd. B", risk: "offline", posture: "none", tip: null, relief: null, peak: 0 },
  { id: "sm-105", name: "Stol 5", room: "105", seat: "A", unit: "Avd. B", risk: "none", posture: "none", tip: 173, relief: null, peak: 0 },
];
const RISK_ORDER = ["offline", "high", "medium", "low", "none"];

function createMockServer(clock = () => Date.now() / 1000) {
  const t0 = clock();
  let alerts, events, wrongPins, lockedUntil;

  function reset() {
    const now = clock();
    alerts = [
      alert("a1", "sm-101", "high", now - 120),
      alert("a2", "sm-104", "offline", now - 900),
    ];
    events = [
      { id: 2, t: now - 900, chip_id: "sm-104", kind: "alert offline", user: null, detail: { alert: "a2", kind: "offline" } },
      { id: 1, t: now - 120, chip_id: "sm-101", kind: "alert high", user: null, detail: { alert: "a1", kind: "high" } },
    ];
    wrongPins = 0;
    lockedUntil = 0;
  }
  function alert(id, chipId, kind, t) {
    return { id, chip_id: chipId, kind, t_raised: t, since: t - 30, t_cleared: null, state: "open", user: null, t_handled: null };
  }
  const mat = (id) => MATS.find((m) => m.id === id);
  const online = (m) => m.risk !== "offline";

  function grid(m, now) {
    if (!online(m) || m.peak === 0) return Array.from({ length: ROWS }, () => Array(COLS).fill(0));
    const drift = Math.sin((now - t0) / 8) * 0.6;
    const cy = 9 + drift, cx = m.posture === "left" ? 5 : m.posture === "right" ? 9.5 : 7;
    return Array.from({ length: ROWS }, (_, r) =>
      Array.from({ length: COLS }, (_, c) => {
        if (r === 0 && c === 0) return null; // a dead cell
        const d2 = ((r - cy) ** 2 + (c - cx) ** 2) / 14;
        return Math.round(Math.max(0, m.peak * Math.exp(-d2) + (r > 3 ? 2 : 0)) * 100) / 100;
      }));
  }
  function snapshot(m, now) {
    if (!online(m)) {
      return { online: false, risk: "offline", posture: "none", time_in_position_s: null, saturated_cells: 0,
        since_relief_s: null, occupied: null, grid: null };
    }
    const occupied = m.peak > 0;
    const g = grid(m, now);
    const hot = [];
    g.forEach((row, r) => row.forEach((v, c) => { if (v !== null && v > 0.75 * m.peak && m.peak > 30) hot.push([r, c]); }));
    return {
      unit: "kPa", scale_max: SCALE_MAX, grid: g, occupied,
      hotspots: hot.length ? [{ id: 1, peak_kpa: m.peak, cells: hot, active_s: 120, persistent: m.risk === "high" }] : [],
      indices: [{ name: "Peak pressure (kPa)", layer: "pressure", value: occupied ? m.peak : null, threshold: 45, near: 36,
        state: m.peak >= 45 ? "over" : m.peak >= 36 ? "near" : "ok" }],
      saturated_cells: m.risk === "high" ? 2 : 0, posture: m.posture,
      time_in_position_s: m.tip === null ? null : m.tip + (now - t0), risk: m.risk, since_relief_s: m.relief,
      online: true, shape: [ROWS, COLS], profile_version: 1,
    };
  }
  function info(m) {
    return { id: m.id, name: m.name, room: m.room, seat: m.seat, unit: m.unit, demo: false };
  }
  function row(m, now) {
    const s = snapshot(m, now);
    return Object.assign(info(m), {
      online: s.online, risk: s.risk, posture: s.posture, time_in_position_s: s.time_in_position_s,
      saturated_cells: s.saturated_cells, saturated: s.saturated_cells >= 1, since_relief_s: s.since_relief_s,
      open_alerts: alerts.filter((a) => a.chip_id === m.id && a.state === "open").length,
    });
  }
  function timeline(m, since, now) {
    if (!online(m)) return [{ t_start: now - 3600, t_end: now - 1800, posture: m.posture, risk: "low" }];
    return [
      { t_start: now - 3600, t_end: now - 2400, posture: "centred", risk: "low" },
      { t_start: now - 2400, t_end: now - 1200, posture: m.posture, risk: m.risk === "low" ? "low" : "medium" },
      { t_start: now - 1200, t_end: now, posture: m.posture, risk: m.risk },
    ].filter((s) => s.t_end >= since);
  }

  const withName = (a) => Object.assign({}, a, { name: mat(a.chip_id) ? mat(a.chip_id).name : a.chip_id });

  function route(req, url, body, now) {
    const path = url.pathname;
    let m;
    if (req.method === "GET") {
      if (path === "/api/health") return [200, { ok: true, time: now, mats: MATS.length, version: "0.1.0" }];
      if (path === "/api/theme") return [200, { palette_light: {}, palette_dark: {}, heatmap_stops: HEATMAP_STOPS }];
      if (path === "/api/overview") {
        const rows = MATS.map((x) => row(x, now));
        rows.sort((a, b) => RISK_ORDER.indexOf(a.risk) - RISK_ORDER.indexOf(b.risk) || (b.time_in_position_s || 0) - (a.time_in_position_s || 0));
        return [200, { time: now, mats: rows, open_alerts: alerts.filter((a) => a.state === "open").length }];
      }
      if (path === "/api/alerts") return [200, { alerts: alerts.map(withName) }];
      if ((m = path.match(/^\/api\/mats\/([^/]+)(\/timeline|\/log)?$/))) {
        const found = mat(decodeURIComponent(m[1]));
        if (!found) return [404, { error: "unknown mat" }];
        if (m[2] === "/log") return [200, { id: found.id, events: events.filter((e) => e.chip_id === found.id) }];
        if (m[2] === "/timeline") {
          const hours = Math.min(Math.max(Number(url.searchParams.get("hours") || 1), 0), 168);
          return [200, { id: found.id, timeline: timeline(found, now - hours * 3600, now) }];
        }
        return [200, Object.assign(info(found), { snapshot: snapshot(found, now), timeline: timeline(found, now - 3600, now),
          alerts: alerts.filter((a) => a.chip_id === found.id) })];
      }
      if (path === "/api/users") return [200, { users: [{ id: 1, name: USER, role: "admin", active: true }], setup: false }];
    }
    if (req.method === "POST" && (m = path.match(/^\/api\/alerts\/([^/]+)\/([^/]+)$/))) {
      if (m[2] !== "ack" && m[2] !== "ignore") return [404, { error: "unknown action" }];
      if (!body || typeof body !== "object") return [400, { error: "send a JSON object" }];
      if (!body.pin) return [401, { error: "PIN required" }];
      if (now < lockedUntil) return [429, { error: "too many wrong PINs, try again later" }];
      if (String(body.pin) !== PIN) {
        if (++wrongPins >= 5) { lockedUntil = now + 30; wrongPins = 0; }
        return [403, { error: "wrong PIN" }];
      }
      wrongPins = 0;
      const a = alerts.find((x) => x.id === m[1]);
      if (!a) return [404, { error: "no open alert with that id" }];
      Object.assign(a, { state: m[2] === "ack" ? "acknowledged" : "ignored", user: USER, t_handled: now });
      return [200, Object.assign({}, a)];
    }
    if (req.method === "POST" && path === "/__mock/reset") { reset(); return [200, { ok: true }]; }
    if (req.method === "POST" && path === "/__mock/raise") {
      if (!body || !mat(body.chip_id)) return [404, { error: "unknown mat" }];
      const a = alert(Math.random().toString(16).slice(2, 14), body.chip_id, body.kind === "offline" ? "offline" : "high", now);
      alerts.push(a);
      return [200, a];
    }
    return [404, { error: "not found" }];
  }

  reset();
  return http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      let body = null;
      try { body = JSON.parse(Buffer.concat(chunks).toString() || "null"); } catch (e) { body = null; }
      const [status, payload] = route(req, new URL(req.url, "http://x"), body, clock());
      res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      res.end(JSON.stringify(payload));
    });
  });
}

module.exports = { createMockServer, PIN, USER };

if (require.main === module) {
  const port = Number(process.env.PORT || 8000);
  createMockServer().listen(port, "0.0.0.0", () => console.log(`SmartMat mock server on http://0.0.0.0:${port} (PIN ${PIN})`));
}
