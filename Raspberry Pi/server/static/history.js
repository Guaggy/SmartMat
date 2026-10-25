"use strict";
// SmartMat dashboard: history playback in the mat panel (loaded before app.js, which owns the shared helpers).
// A "History" mode next to "Live": the saved snapshots of the chosen range are fetched once (GET /api/mats/<id>/history
// with grids, paged by next_from), the grids are decoded once into byte arrays, and the picture is drawn through the same
// HeatMap renderer as the live view. Nothing polls while the mode is on: the page only draws when the cursor moves.
// Leaving the mode stops the timer, drops the data and hands the map back to the live poll.

const H = {
  on: false, id: null, range: 24, speed: 1, peak: false,
  state: "idle",   // idle | loading | ready | empty | off | error
  snaps: [], alerts: [], idx: 0, playing: false, timer: 0, job: 0, capped: false, interval: 300, from: 0, to: 0,
};
const H_RANGES = [6, 24, 72, 168];   // hours
const H_RATES = [2, 6, 15];          // snapshots per second at slow / normal / fast
const H_PAGE = 300;                  // the server's cap with grids
const H_MAX = 2500;                  // about a week of 5 minute snapshots plus alert moments; more is cut (see hCapped)
const H_STRIP_H = 58;

const reposOn = () => store.get("repos") !== "0";   // "Show repositioning info", default on, this browser only
const histRangeText = (h) => t("range_" + h);

function histInit() {
  const r = Number(store.get("hrange")), s = Number(store.get("hspeed"));
  H.range = H_RANGES.includes(r) ? r : 24;
  H.speed = store.get("hspeed") != null && s >= 0 && s < H_RATES.length ? s : 1;
  H.peak = store.get("hpeak") === "1";
  $("modeLive").addEventListener("click", histLeave);
  $("modeHist").addEventListener("click", histEnter);
  $("hRangeSel").addEventListener("change", () => {
    H.range = Number($("hRangeSel").value);
    store.set("hrange", String(H.range));
    renderExport();
    if (H.on) histLoad();
  });
  $("hSpeed").addEventListener("change", () => {
    H.speed = Number($("hSpeed").value);
    store.set("hspeed", String(H.speed));
    if (H.playing) histPlay(true);
  });
  $("hPlay").addEventListener("click", () => histPlay(!H.playing));
  $("hPrev").addEventListener("click", () => { histPlay(false); histGo(H.idx - 1); });
  $("hNext").addEventListener("click", () => { histPlay(false); histGo(H.idx + 1); });
  $("hPrevAlert").addEventListener("click", () => histAlert(-1));
  $("hNextAlert").addEventListener("click", () => histAlert(1));
  $("hScrub").addEventListener("input", () => histGo(Number($("hScrub").value)));
  for (const [id, peak] of [["hInstant", false], ["hPeak", true]]) {
    $(id).addEventListener("click", () => { H.peak = peak; store.set("hpeak", peak ? "1" : "0"); histShow(); });
  }
  const strip = $("hStrip");
  strip.addEventListener("pointerdown", (ev) => { strip.setPointerCapture(ev.pointerId); histSeek(ev); });
  strip.addEventListener("pointermove", (ev) => { if (strip.hasPointerCapture(ev.pointerId)) histSeek(ev); });
  $("exportMenu").addEventListener("toggle", () => { $("exportBox").dataset.sig = ""; renderExport(); });
  window.addEventListener("resize", () => { if (H.on) histStrip(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) histPlay(false); });
}

// ---------- entering and leaving ----------
function histEnter() {
  if (H.on || !S.selected) return;
  Object.assign(H, { on: true, id: S.selected });
  histBlank();
  histChrome();
  renderPanel();
  histLoad();
}
function histLeave() {
  if (!H.on) return;
  histPlay(false);
  H.job++;                                      // an answer still on its way is ignored
  Object.assign(H, { on: false, id: null, state: "idle", snaps: [], alerts: [], idx: 0 });
  S.hm.reset();
  S.mapKey = "";                                // the live picture snaps in instead of tweening from the old one
  histChrome();
  renderPanel();
  fetchMat();
}
function histBlank() { // an empty map (loading, nothing saved): the live picture must not stay on screen
  const snap = S.mat && S.mat.snapshot, rows = snap ? snap.grid.length : 20, cols = snap ? snap.grid[0].length : 20;
  S.hm.set({ grid: Array.from({ length: rows }, () => new Array(cols).fill(0)), scale: 1, snap: true, spots: [], cop: null });
}
function histChrome() { // which parts of the panel belong to which mode
  $("liveTop").hidden = $("liveBot").hidden = H.on;
  $("histTop").hidden = $("histBox").hidden = !H.on;
  for (const [id, on] of [["modeLive", !H.on], ["modeHist", H.on]]) {
    $(id).classList.toggle("on", on);
    $(id).setAttribute("aria-pressed", String(on));
  }
}

// ---------- loading ----------
const flat = (grid) => (grid ? Uint8Array.from(grid.flat()) : null);
async function histLoad() {
  const job = ++H.job, id = H.id;
  histPlay(false);
  Object.assign(H, { state: "loading", snaps: [], alerts: [], idx: 0, capped: false, to: serverNow() });
  H.from = H.to - H.range * 3600;
  histRender();
  let from = H.from, after = "";
  try {
    for (;;) {
      const q = `?with_grids=1&limit=${H_PAGE}&from=${from}&to=${H.to}${after}`;
      const d = await api("/api/mats/" + encodeURIComponent(id) + "/history" + q);
      if (job !== H.job) return;
      if (!d.enabled) { H.state = "off"; break; }
      H.interval = d.interval_s || 300;
      for (const s of d.snapshots) { // decode once: ints 0-255 in a flat byte array, the JSON arrays are dropped
        s.g = flat(s.grid); s.pg = flat(s.peak_grid);
        delete s.grid; delete s.peak_grid;
        H.snaps.push(s);
      }
      if (!d.truncated || d.next_from == null) break;
      if (H.snaps.length >= H_MAX) { H.capped = true; break; }
      from = d.next_from; after = "&after=1";
      setText($("hMsg"), t("hLoading", { n: H.snaps.length }));
    }
  } catch (e) {
    if (job === H.job) { H.state = "error"; histRender(); }
    return;
  }
  if (H.state === "loading") H.state = H.snaps.length ? "ready" : "empty";
  H.alerts = [];
  H.snaps.forEach((s, i) => { if (s.reason !== "periodic") H.alerts.push(i); });
  H.idx = H.snaps.length - 1;
  histRender();
}

// ---------- drawing ----------
function histMessage() {
  if (H.state === "loading") return t("hLoading", { n: H.snaps.length });
  if (H.state === "off") return t("hOff");
  if (H.state === "empty") return t("hEmpty");
  if (H.state === "error") return t("hError");
  return H.capped ? t("hCapped", { n: H.snaps.length }) : "";
}
function histRender() { // the whole history part: after a load, a language or theme change
  if (!H.on) return;
  const ready = H.state === "ready", msg = histMessage();
  setText($("hMsg"), msg);
  $("hMsg").hidden = !msg;
  $("hCtl").hidden = $("hNow").hidden = !ready;
  fillSelect($("hRangeSel"), H_RANGES.map(String), "range_", String(H.range));
  fillSelect($("hSpeed"), ["0", "1", "2"], "spd_", String(H.speed));
  if (!ready) { histBlank(); return; }
  $("hScrub").max = H.snaps.length - 1;
  $("hPeak").textContent = t("hPeakBtn", { n: Math.round(H.interval / 60) });
  histStrip();
  histShow();
}

function histStrip() { // the overview strip: risk colours over time, alert markers; the cursor is a separate element
  const host = $("hStrip"), cv = $("hCanvas"), w = host.clientWidth;
  if (!w || H.state !== "ready") return;
  const dpr = window.devicePixelRatio || 1, ctx = cv.getContext("2d"), span = H.to - H.from;
  cv.width = Math.round(w * dpr); cv.height = Math.round(H_STRIP_H * dpr);
  cv.style.height = H_STRIP_H + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const x = (ts) => ((ts - H.from) / span) * w, fill = { high: "--st-high", medium: "--st-medium", low: "--st-low", none: "--st-none", offline: "--idle" };
  const colour = Object.fromEntries(Object.entries(fill).map(([k, v]) => [k, cssVar(v)]));
  ctx.fillStyle = cssVar("--panel2");
  ctx.fillRect(0, 14, w, 24);
  const BAR_Y = 14, BAR_H = 24;
  H.snaps.forEach((s, i) => {
    const next = H.snaps[i + 1], end = Math.min(next ? next.t : H.to, s.t + 1.6 * H.interval);
    ctx.fillStyle = colour[s.risk] || colour.none;
    ctx.fillRect(x(s.t), BAR_Y, Math.max(1, x(end) - x(s.t)), BAR_H);
  });
  const step = H.range <= 6 ? 3600 : H.range <= 24 ? 4 * 3600 : H.range <= 72 ? 12 * 3600 : 24 * 3600;
  const off = -new Date(H.from * 1000).getTimezoneOffset() * 60;   // tick on local hours
  ctx.font = '11px "Segoe UI", system-ui, sans-serif';
  ctx.textBaseline = "top";
  ctx.fillStyle = cssVar("--muted");
  ctx.strokeStyle = cssVar("--muted");
  ctx.lineWidth = 1;
  const fmt = H.range <= 24 ? { hour: "2-digit", minute: "2-digit" } : { weekday: "short", hour: "2-digit" };
  for (let ts = Math.ceil((H.from + off) / step) * step - off; ts < H.to; ts += step) {
    const px = Math.round(x(ts)) + 0.5, label = new Date(ts * 1000).toLocaleString(locale(), fmt), lw = ctx.measureText(label).width;
    ctx.beginPath(); ctx.moveTo(px, 10); ctx.lineTo(px, BAR_Y); ctx.stroke();
    if (px - lw / 2 > 0 && px + lw / 2 < w) ctx.fillText(label, px - lw / 2, 0);
  }
  ctx.globalAlpha = H.alerts.length > 80 ? 0.55 : 1;   // a busy day stays readable
  for (const i of H.alerts) { // red triangle: alert raised, ring: alert cleared
    const s = H.snaps[i], px = x(s.t), y = BAR_Y + BAR_H + 3;
    ctx.beginPath();
    if (s.reason === "alert_raised") {
      ctx.moveTo(px, y); ctx.lineTo(px - 3.5, y + 8); ctx.lineTo(px + 3.5, y + 8); ctx.closePath();
      ctx.fillStyle = colour.high; ctx.fill();
    } else {
      ctx.arc(px, y + 4, 2.6, 0, 2 * Math.PI);
      ctx.lineWidth = 1.3; ctx.strokeStyle = cssVar("--ink"); ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

function histShow() { // the cursor moved: map, cursor, numbers
  const s = H.snaps[H.idx];
  if (!s) return;
  histMap(s);
  const w = H.to - H.from;
  $("hCursor").style.left = (((s.t - H.from) / w) * 100).toFixed(3) + "%";
  $("hScrub").value = H.idx;
  $("hScrub").setAttribute("aria-valuetext", histWhen(s));
  $("hPrev").disabled = H.idx <= 0;
  $("hNext").disabled = H.idx >= H.snaps.length - 1;
  $("hPrevAlert").disabled = !H.alerts.some((i) => i < H.idx);
  $("hNextAlert").disabled = !H.alerts.some((i) => i > H.idx);
  const hasPeak = !!s.pg;
  for (const [id, on] of [["hInstant", !H.peak], ["hPeak", H.peak]]) {
    $(id).classList.toggle("on", on);
    $(id).setAttribute("aria-pressed", String(on));
  }
  histNumbers(s, hasPeak);
}

function histMap(s) { // the saved grid through the live renderer; hotspots are only a centre here, so a ring is drawn
  const rows = s.rows, cols = s.cols, data = H.peak && s.pg ? s.pg : s.g, scale = s.scale_max || 1, rel = s.unit === "relative";
  $("seat").style.setProperty("--cols", cols);
  $("seat").style.setProperty("--rows", rows);
  $("seat").classList.remove("pick");
  const grid = Array.from({ length: rows }, (_, r) => Array.from({ length: cols }, (_, c) => (data ? (data[r * cols + c] / 255) * scale : 0)));
  const spots = data ? (s.hotspots || []).filter((h) => h.centre).map((h) => ({
    id: h.id, peak: rel ? null : h.peak_kpa, persistent: h.persistent, cells: histBlob(h.centre, h.cells, rows, cols),
  })) : [];
  S.hm.set({ grid, scale, snap: true, spots, cop: null });
  setText($("rampUnit"), rel ? t("mapUnitRel") : t("mapUnit", { n: num(scale, 0) }));
}
function histBlob([cr, cc], n, rows, cols) { // about n cells around the centre: the real shape is not saved
  const rad = Math.max(0.8, Math.sqrt((n || 1) / Math.PI)), cells = [];
  for (let r = Math.max(0, Math.floor(cr - rad)); r <= Math.min(rows - 1, Math.ceil(cr + rad)); r++) {
    for (let c = Math.max(0, Math.floor(cc - rad)); c <= Math.min(cols - 1, Math.ceil(cc + rad)); c++) {
      if (Math.hypot(r - cr, c - cc) <= rad) cells.push([r, c]);
    }
  }
  return cells.length ? cells : [[cr, cc]];
}

const histWhen = (s) => new Date(s.t * 1000).toLocaleString(locale(), { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

// movements in the hour up to `end` from the running counters (a restart makes the counter fall: count from 0 again)
function movesLastHour(rows, end) {
  const win = rows.filter((r) => r.t > end - 3600 && r.t <= end && r.movements != null);
  if (win.length < 2) return null;
  let n = 0;
  for (let i = 1; i < win.length; i++) n += win[i].movements >= win[i - 1].movements ? win[i].movements - win[i - 1].movements : win[i].movements;
  return n;
}

function histNumbers(s, hasPeak) {
  const mat = S.mats.find((m) => m.id === H.id);
  $("hWhen").textContent = histWhen(s) + " ";
  if (mat && mat.demo) $("hWhen").append(el("span", "demo", "DEMO"));
  const ev = $("hEvent");
  const note = s.reason === "alert_raised" || s.reason === "alert_cleared"
    ? t(s.reason === "alert_raised" ? "hRaised" : "hCleared", { k: t("kind_" + (s.alert_kind || "high_risk")) })
    : H.peak && !hasPeak ? t("hNoPeak") : s.g ? "" : t("hNoPicture");
  ev.hidden = !note;
  setText(ev, note);
  ev.className = "hevent" + (s.reason === "alert_raised" ? " raised" : "");
  const rel = s.unit === "relative";
  const pk = (H.peak && s.pg ? Math.max(...s.pg) / 255 * s.scale_max : s.peak_kpa);
  const risk = RISKS.includes(s.risk) || s.risk === "offline" ? s.risk : "none", riskCell = el("span");
  riskCell.append(el("span", "sq " + risk), document.createTextNode(t("risk_" + risk) + (s.score != null ? " (" + num(s.score, 2) + ")" : "")));
  const area = s.contact_area_cm2 != null ? num(s.contact_area_cm2, 0) + " cm²" : s.contact_cells != null ? t("nCells", { n: s.contact_cells }) : "–";
  const pairs = [
    [t("lgRisk"), riskCell],
    [t(rel ? "highestRelative" : "highestPressure"), rel || pk == null ? "–" : num(pk) + " kPa" + (H.peak && s.pg ? " (" + t("hPeakShort") + ")" : "")],
    [t("contactArea"), s.occupied === false ? "–" : area],
    [t("loadIndic"), s.load_kg != null && s.occupied !== false ? "≈ " + num(s.load_kg, 0) + " kg" : "–"],
    [t("lgPosture"), t("p_" + (POSTURES.includes(s.posture) ? s.posture : "none"))],
    [t("timeInPos"), s.time_in_position_s == null ? "–" : dur(s.time_in_position_s)],
  ];
  if (reposOn()) {
    const n = movesLastHour(H.snaps, s.t);
    pairs.push([t("sinceMove"), s.since_movement_s == null ? t("never") : dur(s.since_movement_s)]);
    if (n != null) pairs.push([t("movesHour"), String(n)]);
  }
  const spots = (s.hotspots || []).map((h) => "#" + h.id + (rel ? "" : " " + num(h.peak_kpa) + " kPa") + (h.centre ? " (r" + h.centre[0] + ", c" + h.centre[1] + ")" : ""));
  pairs.push([t("hotspots"), spots.length ? spots.join(", ") : t("none")]);
  kv($("hKv"), pairs, "");
  setText($("hSpotNote"), spots.length ? t("hSpotsApprox") : "");
}

// ---------- moving the cursor, playing ----------
function histGo(i) {
  if (H.state !== "ready") return;
  const n = Math.max(0, Math.min(H.snaps.length - 1, i));
  if (n === H.idx) return;
  H.idx = n;
  histShow();
}
function histSeek(ev) { // a click or drag on the strip: the snapshot nearest in time
  if (H.state !== "ready") return;
  const b = $("hStrip").getBoundingClientRect(), ts = H.from + Math.min(1, Math.max(0, (ev.clientX - b.left) / b.width)) * (H.to - H.from);
  let lo = 0, hi = H.snaps.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (H.snaps[mid].t < ts) lo = mid + 1; else hi = mid; }
  if (lo > 0 && ts - H.snaps[lo - 1].t < H.snaps[lo].t - ts) lo--;
  histGo(lo);
}
function histAlert(dir) {
  const hit = dir < 0 ? [...H.alerts].reverse().find((i) => i < H.idx) : H.alerts.find((i) => i > H.idx);
  if (hit != null) { histPlay(false); histGo(hit); }
}
function histPlay(on) {
  clearInterval(H.timer);
  H.timer = 0;
  H.playing = on && H.state === "ready";
  if (H.playing) {
    if (H.idx >= H.snaps.length - 1) { H.idx = 0; histShow(); }
    H.timer = setInterval(histTick, 1000 / H_RATES[H.speed]);
  }
  const b = $("hPlay");
  b.textContent = "";
  b.append(histIcon(H.playing ? "pause" : "play"));
  b.title = t(H.playing ? "hPause" : "hPlay");
  b.setAttribute("aria-label", b.title);
}
function histTick() {
  if (document.hidden || $("dash").hidden || !H.on) return histPlay(false);
  histGo(H.idx + 1);
  if (H.idx >= H.snaps.length - 1) histPlay(false);
}
function histIcon(kind) {
  const svg = svgEl("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" });
  svg.append(svgEl("path", { d: kind === "play" ? "M8 5v14l11-7z" : "M7 5h4v14H7zM13 5h4v14h-4z" }));
  return svg;
}

// ---------- export menu (plain download links) ----------
function renderExport() {
  const box = $("exportBox"), row = S.mats.find((m) => m.id === S.selected);
  if (!row) return;
  const repos = reposOn(), sig = [lang, row.id, H.range, repos].join("|");
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  box.textContent = "";
  const to = Math.floor(serverNow()), from = to - H.range * 3600, id = encodeURIComponent(row.id);
  const link = (label, file) => {
    const a = el("a", "", label);
    a.href = `/api/mats/${id}/${file}?from=${from}&to=${to}`;
    a.download = "";
    return a;
  };
  box.append(link(t("exHistory"), "history.csv"));
  if (repos) box.append(link(t("exRepos"), "repositioning.csv"));
  box.append(el("p", "muted small", t("exHint", { r: histRangeText(H.range) })));
}
