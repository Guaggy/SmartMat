"use strict";
// SmartMat dashboard. Plain JS, no build step. Everything that comes from the API is written with
// textContent / setAttribute / canvas, never innerHTML (names and rooms are typed in by people).

// ---------- text (Norwegian bokmaal first, English on toggle) ----------
const i18n = {
  nb: {
    unitFilter: "Filtrer på avdeling", allUnits: "Alle avdelinger", sortBy: "Sorter etter",
    sortRisk: "Risiko", sortRoom: "Rom", sortDevice: "Enhet", sortTime: "Tid i stilling",
    searchPh: "Søk rom, enhet, sete", alerts: "Varsler", help: "Hjelp", back: "Tilbake",
    colDevice: "Enhet", colRoom: "Rom", colSeat: "Sete", colOk: "Data OK", colStatus: "Status",
    dark: "Mørk", light: "Lys", langBtn: "English",
    p_left: "Venstre side", p_right: "Høyre side", p_forward: "Lent fremover", p_centred: "Sentrert", p_none: "Ingen bruker",
    statusNone: "Ingen bruker i {t}", offline: "Frakoblet, ingen data", alertFlag: "Varsel",
    dataOk: "Data OK", dataLost: "Ingen data",
    risk_high: "Høy risiko", risk_medium: "Middels risiko", risk_low: "Lav risiko", risk_none: "Ingen bruker", risk_offline: "Frakoblet",
    h: "t", min: "min", ago: "{t} siden",
    pressureMap: "Trykkart", front: "Foran", low: "Lav", high: "Høy", edit: "Rediger", toList: "Til listen",
    highestPressure: "Høyeste trykk", highestRelative: "Høyeste signal", sinceRelief: "Tid siden avlastning",
    timeInPos: "Tid i stilling", lastData: "Siste data", hotspots: "Hotspots", indices: "Indikatorer", none: "Ingen",
    persistent: "vedvarende", activeFor: "aktiv {t}",
    idx_ok: "OK", idx_near: "Nær grensen", idx_over: "Over grensen",
    selectMat: "Velg en mat i listen for å se trykkart.", noMats: "Ingen matter funnet.",
    saturation: "{n} celler ved sensorgrensen: last og topp leses for lavt",
    uncal: "Ikke kalibrert: relativt signal, ikke trykk.",
    staleMat: "Ingen nye data på {t}. Bildet er gammelt.", offlineMat: "Matten er frakoblet. Bildet viser siste kjente data.",
    lostServer: "Ingen kontakt med serveren. Statusene under kan være gamle.",
    unoccupied: "Ingen bruker på matten.", mapUnit: "{n} kPa full farge", mapUnitRel: "relativt signal",
    noAlerts: "Ingen varsler.", kind_high_risk: "Høy risiko", kind_offline: "Frakoblet",
    raised: "utløst for {t} siden", st_open: "Åpen", st_acknowledged: "Bekreftet", st_ignored: "Ignorert", byUser: "av {u}",
    ack: "Bekreft", ignore: "Ignorer", pin: "PIN", cancel: "Avbryt", ok: "OK",
    dlgAck: "Bekreft varsel: {name}", dlgIgnore: "Ignorer varsel: {name}", dlgEdit: "Rediger mat",
    fName: "Navn", fRoom: "Rom", fSeat: "Sete", fUnit: "Avdeling",
    ackBy: "Bekreftet av {u}", ignBy: "Ignorert av {u}", savedBy: "Lagret av {u}", netErr: "Ingen kontakt med serveren.",
    tlTitle: "Siste {n} timer", lgNoData: "Ingen data", lgHandled: "Håndtert (bekreftet eller ignorert)", showMap: "Vis trykkart",
    handledBy: "Håndtert av {u}",
    users: "Brukere", close: "Lukk", addUser: "Ny bruker", disable: "Deaktiver", enable: "Aktiver", resetPin: "Ny PIN",
    roleAdmin: "Administrator", roleUser: "Sykepleier", userOff: "deaktivert", fRole: "Rolle",
    fNewPin: "Ny PIN (4-8 siffer)", fRepeatPin: "Gjenta PIN", adminPin: "Din PIN (administrator)",
    dlgFirst: "Opprett første bruker (admin)", firstHint: "Det finnes ingen brukere ennå. Denne personen blir administrator.",
    dlgAddUser: "Ny bruker", dlgDisable: "Deaktiver {n}", dlgEnable: "Aktiver {n}", dlgResetPin: "Ny PIN for {n}",
    pinMismatch: "PIN-kodene er ikke like.", userAdded: "Bruker {n} opprettet", userChanged: "Endret av {u}",
    foot: "Ingeniørverktøy, ikke medisinsk utstyr. Stilling og risiko er heuristikker. Bruk sammen med vanlig klinisk vurdering.",
    help_: {
      title: "Hjelp",
      colours: ["Hva fargene betyr", [
        ["high", "Høy risiko", "Trykket er over grensen. Se til personen og avlast."],
        ["medium", "Middels risiko", "Trykket eller tiden i samme stilling nærmer seg grensen."],
        ["low", "Lav risiko", "Ingen grenser er nådd akkurat nå."],
        ["none", "Ingen bruker", "Matten sender data, men det sitter ingen på den."],
        ["offline", "Frakoblet", "Matten har sluttet å sende. Da vet vi ingenting om personen. En stille mat vises aldri som grønn."],
      ]],
      alert: ["Hva gjør jeg ved et varsel", [
        "Trykk på bjella øverst. Rødt tall viser antall åpne varsler.",
        "Gå til rommet og se til personen. Avlast eller hjelp til med å skifte stilling etter lokale rutiner.",
        "Trykk Bekreft og skriv inn din PIN når du har tatt hånd om det. Bruk Ignorer hvis varselet er feil eller ikke relevant.",
        "Navnet ditt lagres sammen med handlingen og vises som en rød markør i tidslinjen.",
        "Frakoblet mat: sjekk strøm og nettverk, og se til personen på vanlig måte.",
      ]],
      map: ["Trykkartet", [
        "Fargene viser trykk i kPa fra lav (lys) til høy (mørk rød). «Foran» er forkanten av sittefladen.",
        "Stiplet ramme markerer et hotspot, et område med høyt trykk over tid.",
        "«Celler ved sensorgrensen» betyr at sensoren metter. Last og toppverdi er da høyere enn det som vises.",
        "Tid siden avlastning er tiden siden trykket sist ble tydelig flyttet eller tatt av.",
        "Tidslinjen under en rad viser stilling og risiko de siste timene. Tomme felt betyr at vi ikke har data.",
      ]],
      note: ["Viktig", [
        "SmartMat er et ingeniørverktøy, ikke et medisinsk utstyr.",
        "Last i kg er et grovt estimat. Stilling og risiko er heuristikker som brukes til å teste måleløypa, ikke en diagnose og ikke en validert risikoscore.",
        "Bruk alltid sammen med vanlig klinisk vurdering og lokale rutiner. Demo-matter er innspilte data og viser ingen ekte person.",
      ]],
    },
  },
  en: {
    unitFilter: "Filter by unit", allUnits: "All units", sortBy: "Sort by",
    sortRisk: "Risk", sortRoom: "Room", sortDevice: "Device", sortTime: "Time in position",
    searchPh: "Search room, device, seat", alerts: "Alerts", help: "Help", back: "Back",
    colDevice: "Device", colRoom: "Room", colSeat: "Seat", colOk: "Data OK", colStatus: "Status",
    dark: "Dark", light: "Light", langBtn: "Norsk",
    p_left: "Left side", p_right: "Right side", p_forward: "Leaning forward", p_centred: "Centred", p_none: "No user",
    statusNone: "No user for {t}", offline: "Offline, no data", alertFlag: "Alert",
    dataOk: "Data OK", dataLost: "No data",
    risk_high: "High risk", risk_medium: "Medium risk", risk_low: "Low risk", risk_none: "No user", risk_offline: "Offline",
    h: "h", min: "min", ago: "{t} ago",
    pressureMap: "Pressure map", front: "Front", low: "Low", high: "High", edit: "Edit", toList: "To the list",
    highestPressure: "Highest pressure", highestRelative: "Highest signal", sinceRelief: "Time since relief",
    timeInPos: "Time in position", lastData: "Last data", hotspots: "Hotspots", indices: "Indices", none: "None",
    persistent: "persistent", activeFor: "active {t}",
    idx_ok: "OK", idx_near: "Near limit", idx_over: "Over limit",
    selectMat: "Pick a mat in the list to see its pressure map.", noMats: "No mats found.",
    saturation: "{n} cells at sensor limit: load and peak read low",
    uncal: "Not calibrated: relative signal, not pressure.",
    staleMat: "No new data for {t}. This picture is old.", offlineMat: "The mat is offline. The picture shows the last known data.",
    lostServer: "No contact with the server. The statuses below may be old.",
    unoccupied: "Nobody is on the mat.", mapUnit: "{n} kPa full colour", mapUnitRel: "relative signal",
    noAlerts: "No alerts.", kind_high_risk: "High risk", kind_offline: "Offline",
    raised: "raised {t} ago", st_open: "Open", st_acknowledged: "Acknowledged", st_ignored: "Ignored", byUser: "by {u}",
    ack: "Acknowledge", ignore: "Ignore", pin: "PIN", cancel: "Cancel", ok: "OK",
    dlgAck: "Acknowledge alert: {name}", dlgIgnore: "Ignore alert: {name}", dlgEdit: "Edit mat",
    fName: "Name", fRoom: "Room", fSeat: "Seat", fUnit: "Unit",
    ackBy: "Acknowledged by {u}", ignBy: "Ignored by {u}", savedBy: "Saved by {u}", netErr: "No contact with the server.",
    tlTitle: "Last {n} hours", lgNoData: "No data", lgHandled: "Handled (acknowledged or ignored)", showMap: "Show pressure map",
    handledBy: "Handled by {u}",
    users: "Users", close: "Close", addUser: "Add user", disable: "Disable", enable: "Enable", resetPin: "Reset PIN",
    roleAdmin: "Admin", roleUser: "Nurse", userOff: "disabled", fRole: "Role",
    fNewPin: "New PIN (4-8 digits)", fRepeatPin: "Repeat PIN", adminPin: "Your PIN (admin)",
    dlgFirst: "Create first user (admin)", firstHint: "There are no users yet. This person becomes the administrator.",
    dlgAddUser: "Add user", dlgDisable: "Disable {n}", dlgEnable: "Enable {n}", dlgResetPin: "Reset PIN for {n}",
    pinMismatch: "The PINs do not match.", userAdded: "User {n} added", userChanged: "Changed by {u}",
    foot: "Engineering aid, not a medical device. Posture and risk are heuristics. Use alongside normal clinical assessment.",
    help_: {
      title: "Help",
      colours: ["What the colours mean", [
        ["high", "High risk", "Pressure is over the limit. Check on the person and relieve the pressure."],
        ["medium", "Medium risk", "Pressure or time in the same position is getting close to the limit."],
        ["low", "Low risk", "No limits are reached right now."],
        ["none", "No user", "The mat is sending data, but nobody is sitting on it."],
        ["offline", "Offline", "The mat stopped sending. We know nothing about the person then. A silent mat is never shown as green."],
      ]],
      alert: ["What to do on an alert", [
        "Tap the bell at the top. The red number is the count of open alerts.",
        "Go to the room and check on the person. Relieve the pressure or help them change position, following local routines.",
        "Tap Acknowledge and enter your PIN once it is dealt with. Use Ignore if the alert is wrong or not relevant.",
        "Your name is saved with the action and shows as a red marker in the timeline.",
        "Offline mat: check power and network, and check on the person as usual.",
      ]],
      map: ["The pressure map", [
        "Colours show pressure in kPa from low (light) to high (dark red). \"Front\" is the front edge of the seat.",
        "A dashed outline marks a hotspot, an area of high pressure over time.",
        "\"Cells at sensor limit\" means the sensor saturates. Load and peak are then higher than shown.",
        "Time since relief is the time since the pressure was last clearly moved or taken off.",
        "The timeline under a row shows posture and risk for the last hours. Empty parts mean we have no data.",
      ]],
      note: ["Important", [
        "SmartMat is an engineering aid, not a medical device.",
        "Load in kg is a rough estimate. Posture and risk are heuristics for testing the pipeline, not a diagnosis and not a validated risk score.",
        "Always use alongside normal clinical assessment and local routines. Demo mats are recorded data and show no real person.",
      ]],
    },
  },
};

// ---------- small helpers ----------
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const setText = (node, s) => { if (node.textContent !== s) node.textContent = s; };
const store = {
  get(k) { try { return localStorage.getItem("sm." + k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem("sm." + k, v); } catch (e) { /* private mode: just not remembered */ } },
};

let lang = store.get("lang") === "en" ? "en" : "nb";
const t = (key, vars) => {
  let s = i18n[lang][key] ?? i18n.nb[key] ?? key;
  for (const k in vars || {}) s = s.replace("{" + k + "}", vars[k]);
  return s;
};
const locale = () => (lang === "en" ? "en-GB" : "nb-NO");

// 45 s, 11:58 min, 58 min, 1 h 17 min (nb: 1 t 17 min)
function dur(s) {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60);
  if (s < 60) return s + " s";
  if (s < 1200) return m + ":" + String(s % 60).padStart(2, "0") + " " + t("min");
  if (m < 60) return m + " " + t("min");
  return Math.floor(m / 60) + " " + t("h") + " " + (m % 60) + " " + t("min");
}
const num = (v, d = 1) => v.toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d });
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });

// ---------- state ----------
const RISK_ORDER = { offline: 0, high: 1, medium: 2, low: 3, none: 4 };
const RISKS = ["high", "medium", "low", "none"];
const S = {
  mats: [], openAlerts: 0, alerts: [], timeline: null, mat: null, offset: 0, lost: false,
  selected: null, open: false, bellOpen: false, needsAdmin: false, setupShown: false,
  sort: store.get("sort") || "risk", unit: store.get("unit") || "", q: "",
  ramp: [[0, [207, 230, 222]], [0.25, [126, 189, 168]], [0.5, [233, 196, 106]], [0.75, [224, 123, 57]], [0.9, [179, 38, 30]], [1, [107, 15, 26]]],
};
const rows = new Map(); // mat id -> {row, head, parts...}
const serverNow = () => Date.now() / 1000 + S.offset;

// ---------- API ----------
async function api(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw Object.assign(new Error(r.statusText), { status: r.status });
  return r.json();
}
// Writes always carry a PIN (except creating the very first user); the server answers {ok, user, ...} or {error}.
async function send(method, path, body) {
  try {
    const r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    return r.ok ? Object.assign({ ok: true }, data) : { ok: false, error: data.error || r.statusText };
  } catch (e) {
    return { ok: false, error: t("netErr") };
  }
}
// Run fn every ms (not while the tab is hidden, never two at once). Returns a "run now" function.
function every(ms, fn) {
  let busy = false;
  const run = async () => {
    if (busy || document.hidden) return;
    busy = true;
    try { await fn(); } catch (e) { /* each fn handles its own errors */ } finally { busy = false; }
  };
  setInterval(run, ms);
  run();
  return run;
}

// ---------- list ----------
const byTime = (a, b) => (b.time_in_position_s || 0) - (a.time_in_position_s || 0);
const byName = (a, b) => a.name.localeCompare(b.name, lang, { numeric: true });
const SORTS = {
  risk: (a, b) => (RISK_ORDER[a.risk] ?? 5) - (RISK_ORDER[b.risk] ?? 5) || byTime(a, b),
  room: (a, b) => (a.room || "").localeCompare(b.room || "", lang, { numeric: true }) || byName(a, b),
  device: byName,
  time: byTime,
};

function statusOf(m) {
  if (m.risk === "offline" || !m.online) return { cls: "offline", text: t("offline") };
  if (m.risk === "none" || m.posture === "none") return { cls: "none", text: t("statusNone", { t: dur(m.time_in_position_s) }) };
  const cls = RISKS.includes(m.risk) ? m.risk : "none"; // an unknown risk is never shown as green
  return { cls, text: t("p_" + m.posture) + " > " + dur(m.time_in_position_s) };
}

function makeRow(id) {
  const row = el("div", "row");
  const head = el("button", "head");
  head.type = "button";
  const dev = el("span", "c-dev"), name = el("b"), demo = el("span", "demo", "DEMO"), flag = el("span", "flag");
  dev.append(name, demo, flag);
  const room = el("span", "c-room"), seat = el("span", "c-seat"), ok = el("span", "c-ok"), st = el("span", "status");
  head.append(dev, room, seat, ok, st);
  const detail = el("div", "detail");
  detail.hidden = true;
  const cap = el("div", "cap"), capText = el("span"), toMap = el("button", "link only-narrow");
  toMap.type = "button";
  cap.append(capText, toMap);
  const tlHost = el("div");
  const legend = el("div", "legend");
  detail.append(cap, tlHost, legend);
  row.append(head, detail);
  head.addEventListener("click", () => select(id));
  toMap.addEventListener("click", () => $("pm").scrollIntoView());
  const r = { row, head, name, demo, flag, room, seat, ok, st, detail, capText, toMap, tlHost, legend, legendLang: null };
  rows.set(id, r);
  return r;
}

function updateRow(r, m) {
  const sel = m.id === S.selected, st = statusOf(m);
  r.row.classList.toggle("sel", sel);
  r.head.setAttribute("aria-expanded", String(sel && S.open));
  r.head.title = m.id;
  setText(r.name, m.name);
  r.demo.hidden = !m.demo;
  r.flag.hidden = !(m.open_alerts > 0);
  setText(r.flag, t("alertFlag"));
  setText(r.room, m.room || "");
  r.room.dataset.l = t("colRoom");
  setText(r.seat, m.seat || "");
  r.seat.dataset.l = t("colSeat");
  const good = m.online && !S.lost;
  setText(r.ok, good ? "✓" : "✕");
  r.ok.className = "c-ok " + (good ? "yes" : "no");
  r.ok.setAttribute("aria-label", good ? t("dataOk") : t("dataLost"));
  setText(r.st, st.text);
  r.st.className = "status " + st.cls;
  const open = sel && S.open;
  r.detail.hidden = !open;
  if (open) {
    setText(r.capText, t("tlTitle", { n: 5 }));
    setText(r.toMap, t("showMap"));
    if (r.legendLang !== lang) { buildLegend(r.legend); r.legendLang = lang; }
    drawTimeline(r.tlHost);
  }
}

function buildLegend(host) {
  host.textContent = "";
  for (const k of RISKS) {
    const item = el("span");
    item.append(el("span", "sq " + k), document.createTextNode(t("risk_" + k)));
    host.append(item);
  }
  const nodata = el("span"), handled = el("span");
  nodata.append(el("span", "sq hollow"), document.createTextNode(t("lgNoData")));
  handled.append(el("span", "sq mk"), document.createTextNode(t("lgHandled")));
  host.append(nodata, handled);
}

function renderList() {
  const q = S.q.trim().toLowerCase();
  const shown = S.mats
    .filter((m) => !S.unit || m.unit === S.unit)
    .filter((m) => !q || [m.name, m.room, m.seat, m.id].some((v) => (v || "").toLowerCase().includes(q)))
    .sort(SORTS[S.sort] || SORTS.risk);
  const seen = new Set();
  const box = $("rows");
  shown.forEach((m, i) => {
    const r = rows.get(m.id) || makeRow(m.id);
    if (box.children[i] !== r.row) box.insertBefore(r.row, box.children[i] || null);
    updateRow(r, m); // after insertion: the timeline measures its width
    seen.add(m.id);
  });
  for (const [id, r] of rows) if (!seen.has(id)) { r.row.remove(); rows.delete(id); }
  $("empty").hidden = shown.length > 0;
  setText($("empty"), t("noMats"));
  // first load: show some mat in the pressure panel without opening its timeline
  if (!S.mats.some((m) => m.id === S.selected) && shown.length) { S.selected = shown[0].id; S.open = false; S.mat = null; renderList(); fetchMat(); }
}

function renderUnits() {
  const units = [...new Set(S.mats.map((m) => m.unit).filter(Boolean))].sort();
  const sel = $("unit");
  if ([...sel.options].slice(1).map((o) => o.value).join("|") === units.join("|")) return;
  while (sel.options.length > 1) sel.remove(1);
  for (const u of units) { const o = el("option", "", u); o.value = u; sel.append(o); }
  sel.value = units.includes(S.unit) ? S.unit : "";
}

function select(id) {
  if (S.selected === id) S.open = !S.open;
  else { S.selected = id; S.open = true; S.mat = null; S.timeline = null; }
  renderList();
  renderPanel();
  fetchMat();
  fetchTimeline();
}

// ---------- timeline (SVG) ----------
const SVGNS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs, cls) => {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (cls) e.setAttribute("class", cls);
  return e;
};

function drawTimeline(host) {
  host.textContent = "";
  const tl = S.timeline;
  if (!tl || tl.id !== S.selected) return;
  const W = Math.max(280, host.clientWidth), BAR = 40, H = BAR + 18;
  const now = serverNow(), t0 = now - tl.hours * 3600;
  const x = (ts) => ((Math.max(t0, Math.min(now, ts)) - t0) / (now - t0)) * W;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img" }, "tl");
  svg.setAttribute("aria-label", t("tlTitle", { n: tl.hours }));
  svg.append(svgEl("rect", { x: 0.5, y: 0.5, width: W - 1, height: BAR }, "tl-track"));
  for (let h = Math.ceil(t0 / 3600) * 3600; h < now; h += 3600) {
    svg.append(svgEl("line", { x1: x(h), x2: x(h), y1: 0, y2: BAR + 4 }, "tick"));
    const label = svgEl("text", { x: x(h), y: H - 3, "text-anchor": x(h) > W - 20 ? "end" : x(h) < 20 ? "start" : "middle" });
    label.textContent = clock(h);
    svg.append(label);
  }
  for (const s of tl.segments) {
    if (s.t_end <= t0) continue;
    const x1 = x(s.t_start), w = Math.max(1, x(s.t_end) - x1);
    const risk = RISKS.includes(s.risk) ? s.risk : "none";
    const g = svgEl("g", {}, "seg " + risk);
    g.append(svgEl("rect", { x: x1, y: 1, width: w, height: BAR - 1 }));
    const title = svgEl("title");
    title.textContent = `${t("p_" + s.posture)}, ${t("risk_" + risk)}, ${clock(s.t_start)} - ${clock(s.t_end)}`;
    g.append(title);
    if (w > 80) {
      const label = svgEl("text", { x: x1 + 6, y: BAR / 2 + 4 });
      label.textContent = t("p_" + s.posture);
      g.append(label);
    }
    svg.append(g);
  }
  for (const mk of tl.markers) {
    if (mk.t < t0) continue;
    const g = svgEl("g", {}, "mark");
    g.append(svgEl("line", { x1: x(mk.t), x2: x(mk.t), y1: 0, y2: BAR + 6 }), svgEl("rect", { x: x(mk.t) - 3, y: BAR + 4, width: 7, height: 7 }));
    const title = svgEl("title");
    title.textContent = t("handledBy", { u: mk.user }) + ", " + clock(mk.t);
    g.append(title);
    svg.append(g);
  }
  host.append(svg);
}

async function fetchTimeline() {
  const id = S.selected;
  if (!id || !S.open) return;
  try {
    const tl = await api("/api/mats/" + encodeURIComponent(id) + "/timeline?hours=5");
    if (id !== S.selected) return;
    S.timeline = Object.assign(tl, { id, hours: 5 });
    const r = rows.get(id);
    if (r && !r.detail.hidden) drawTimeline(r.tlHost);
  } catch (e) { /* keep the last drawing */ }
}

// ---------- pressure panel ----------
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function hexRgb(h) { const n = parseInt(h.replace("#", ""), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }

function ramp(v, bg) { // v 0..1 -> [r,g,b]; below ~2 % of full scale it fades into the background
  v = Math.max(0, Math.min(1, v));
  const s = S.ramp;
  let i = 1;
  while (i < s.length - 1 && v > s[i][0]) i++;
  const f = Math.max(0, Math.min(1, (v - s[i - 1][0]) / (s[i][0] - s[i - 1][0] || 1)));
  const mix = Math.min(1, v / 0.04);
  return [0, 1, 2].map((k) => (s[i - 1][1][k] + (s[i][1][k] - s[i - 1][1][k]) * f) * mix + bg[k] * (1 - mix));
}

function drawMap(snap) {
  const canvas = $("map"), K = 8, rowsN = snap.grid.length, colsN = snap.grid[0].length;
  canvas.width = colsN * K;
  canvas.height = rowsN * K;
  const ctx = canvas.getContext("2d"), img = ctx.createImageData(canvas.width, canvas.height), bg = hexRgb(cssVar("--hm-bg"));
  const at = (r, c) => snap.grid[Math.max(0, Math.min(rowsN - 1, r))][Math.max(0, Math.min(colsN - 1, c))] ?? 0;
  for (let y = 0; y < canvas.height; y++) {
    const fy = (y + 0.5) / K - 0.5, r0 = Math.floor(fy), ty = fy - r0;
    for (let xp = 0; xp < canvas.width; xp++) {
      const fx = (xp + 0.5) / K - 0.5, c0 = Math.floor(fx), tx = fx - c0;
      const top = at(r0, c0) * (1 - tx) + at(r0, c0 + 1) * tx, bot = at(r0 + 1, c0) * (1 - tx) + at(r0 + 1, c0 + 1) * tx;
      const rgb = ramp((top * (1 - ty) + bot * ty) / snap.scale_max, bg), p = (y * canvas.width + xp) * 4;
      img.data.set([rgb[0], rgb[1], rgb[2], 255], p);
    }
  }
  ctx.putImageData(img, 0, 0);
  // hotspots: dashed ink outline round each area on a solid halo, so it reads on any colour
  for (const spot of snap.hotspots) {
    const key = (r, c) => r + "," + c, inside = new Set(spot.cells.map(([r, c]) => key(r, c)));
    const path = new Path2D();
    for (const [r, c] of spot.cells) {
      const x0 = c * K + 1, y0 = r * K + 1, x1 = x0 + K - 2, y1 = y0 + K - 2; // edges with no neighbour in the same area
      if (!inside.has(key(r - 1, c))) { path.moveTo(x0, y0); path.lineTo(x1, y0); }
      if (!inside.has(key(r + 1, c))) { path.moveTo(x0, y1); path.lineTo(x1, y1); }
      if (!inside.has(key(r, c - 1))) { path.moveTo(x0, y0); path.lineTo(x0, y1); }
      if (!inside.has(key(r, c + 1))) { path.moveTo(x1, y0); path.lineTo(x1, y1); }
    }
    ctx.setLineDash([]);
    ctx.lineWidth = spot.persistent ? 4 : 3;
    ctx.strokeStyle = cssVar("--panel");
    ctx.stroke(path);
    ctx.setLineDash([3, 2]);
    ctx.lineWidth = spot.persistent ? 2 : 1.4;
    ctx.strokeStyle = cssVar("--ink");
    ctx.stroke(path);
  }
}

function kv(host, pairs, empty) {
  host.textContent = "";
  if (!pairs.length) pairs = [[empty, ""]];
  for (const [k, v] of pairs) {
    const wrap = el("div"), dt = el("dt"), dd = el("dd");
    if (k instanceof Node) dt.append(k); else dt.textContent = k;
    if (v instanceof Node) dd.append(v); else dd.textContent = v;
    wrap.append(dt, dd);
    host.append(wrap);
  }
}

function renderPanel() {
  const row = S.mats.find((m) => m.id === S.selected);
  $("editBtn").hidden = !row;
  $("pmBody").hidden = !row;
  if (!row) { setText($("pmSub"), t("selectMat")); return; }
  const d = S.mat && S.mat.id === row.id ? S.mat : row, snap = S.mat && S.mat.id === row.id ? S.mat.snapshot : null;
  const stale = S.lost || !row.online || (S.mat && S.mat.id === row.id && S.mat.stale);
  const sub = $("pmSub");
  sub.textContent = [row.name, row.room, row.seat].filter(Boolean).join(" · ") + " ";
  if (row.demo) sub.append(el("span", "demo", "DEMO"));
  $("pm").classList.toggle("stale", !!stale);
  const age = S.mat && S.mat.id === row.id ? S.mat.age_s : null;
  const staleNote = $("pmStale");
  staleNote.hidden = !stale;
  setText(staleNote, S.lost ? t("lostServer") : !row.online ? t("offlineMat") : t("staleMat", { t: dur(age || 0) }));

  const rel = snap && snap.unit === "relative";
  const unocc = snap && snap.occupied === false;
  const sat = d.saturated_cells || 0;
  setText($("pmSat"), t("saturation", { n: sat }));
  $("pmSat").hidden = !(sat > 0);
  setText($("pmUncal"), unocc ? t("unoccupied") : t("uncal"));
  $("pmUncal").hidden = !(rel || unocc);
  if (snap) {
    drawMap(snap);
    setText($("rampUnit"), rel ? t("mapUnitRel") : t("mapUnit", { n: num(snap.scale_max, 0) }));
  }
  setText($("peakK"), rel ? t("highestRelative") : t("highestPressure"));
  const peak = snap && snap.peak_kpa != null && !unocc ? snap.peak_kpa : null;
  const hasPeak = peak != null && !rel;
  setText($("peakV"), hasPeak ? num(peak) : "–");
  if (hasPeak) { const u = el("small", "", " kPa"); $("peakV").append(u); }
  setText($("reliefV"), row.since_relief_s == null || stale ? "–" : dur(row.since_relief_s));

  kv($("pmKv"), [
    [t("timeInPos"), stale ? "–" : dur(row.time_in_position_s)],
    [t("lastData"), age == null ? "–" : t("ago", { t: dur(age) })],
  ]);
  kv($("pmSpots"), (snap ? snap.hotspots : []).map((h) => [
    "#" + h.id + " " + num(h.peak_kpa) + " kPa",
    t("activeFor", { t: dur(h.active_s) }) + (h.persistent ? ", " + t("persistent") : ""),
  ]), t("none"));
  kv($("pmIdx"), (snap ? snap.indices : []).map((ix) => {
    const k = el("span");
    k.append(el("span", "sq " + ix.state), document.createTextNode(ix.name));
    return [k, (ix.value == null ? "–" : num(ix.value)) + " / " + ix.threshold + "  " + t("idx_" + ix.state)];
  }), t("none"));
}

async function fetchMat() {
  const id = S.selected;
  if (!id) return;
  try {
    const m = await api("/api/mats/" + encodeURIComponent(id));
    if (id !== S.selected) return;
    S.mat = m;
  } catch (e) {
    if (e.status === 404) { S.selected = null; S.mat = null; }
  }
  renderPanel();
}

// ---------- bell and alerts ----------
function renderBell() {
  const badge = $("badge");
  badge.hidden = !(S.openAlerts > 0);
  setText(badge, String(S.openAlerts));
  $("bell").setAttribute("aria-label", t("alerts") + ", " + S.openAlerts);
  $("bellpanel").hidden = !S.bellOpen;
  $("bell").setAttribute("aria-expanded", String(S.bellOpen));
  if (!S.bellOpen) return;
  const list = $("alertList");
  const sorted = [...S.alerts].sort((a, b) => (a.state === "open" ? 0 : 1) - (b.state === "open" ? 0 : 1) || b.t_raised - a.t_raised).slice(0, 30);
  // rebuild only on change (ages count in whole minutes), so a click is never lost to a refresh
  const sig = lang + sorted.map((a) => [a.id, a.state, a.by, Math.floor((serverNow() - a.t_raised) / 60)]).join("|");
  if (list.dataset.sig === sig) return;
  list.dataset.sig = sig;
  list.textContent = "";
  if (!sorted.length) list.append(el("li", "al muted", t("noAlerts")));
  for (const a of sorted) {
    const li = el("li", "al"), head = el("div"), meta = el("div", "muted");
    head.append(el("b", "", a.name), document.createTextNode(a.room ? " · " + a.room : ""));
    const sq = el("span", "sq " + (a.state === "open" ? (a.kind === "offline" ? "offline" : "high") : "none"));
    meta.append(sq, document.createTextNode(
      t("kind_" + a.kind) + " · " + t("raised", { t: dur(serverNow() - a.t_raised) }) + " · " + t("st_" + a.state) + (a.by ? " " + t("byUser", { u: a.by }) : "")));
    li.append(head, meta);
    if (a.state === "open") {
      const acts = el("div", "acts"), ack = el("button", "btn primary", t("ack")), ign = el("button", "btn", t("ignore"));
      ack.type = ign.type = "button";
      ack.addEventListener("click", () => handleAlert("ack", a));
      ign.addEventListener("click", () => handleAlert("ignore", a));
      acts.append(ack, ign);
      li.append(acts);
    }
    list.append(li);
  }
}

function setBell(open) {
  S.bellOpen = open;
  if (open) $("bellpanel").style.top = document.querySelector(".top").offsetHeight + "px";
  renderBell();
  if (open) loadAlerts();
}

function handleAlert(kind, a) {
  writeDialog({
    title: t(kind === "ack" ? "dlgAck" : "dlgIgnore", { name: a.name }),
    send: (v) => send("POST", "/api/alerts/" + encodeURIComponent(a.id) + "/" + kind, { pin: v.pin }),
    done: (res) => toast(t(kind === "ack" ? "ackBy" : "ignBy", { u: res.user })),
  });
}

// ---------- PIN dialog and toast ----------
let dialogJob = null;
// fields: {key, label, value, type: "password", options: [[value, text]]}; noPin hides the acting user's PIN box
function writeDialog({ title, fields = [], send, done, pinLabel, noPin, hint }) {
  $("dlgTitle").textContent = title;
  const box = $("dlgFields");
  box.textContent = "";
  if (hint) box.append(el("p", "muted", hint));
  for (const f of fields) {
    const label = el("label", "", f.label), input = el(f.options ? "select" : "input");
    for (const [v, text] of f.options || []) { const o = el("option", "", text); o.value = v; input.append(o); }
    if (f.type) input.type = f.type;
    if (f.type === "password") input.setAttribute("inputmode", "numeric");
    input.value = f.value || (f.options ? f.options[0][0] : "");
    input.name = f.key;
    input.autocomplete = "off";
    label.append(input);
    box.append(label);
  }
  $("pinRow").hidden = !!noPin;
  $("pin").required = !noPin;
  $("pinLabel").textContent = pinLabel || t("pin");
  $("pin").value = "";
  $("dlgErr").textContent = "";
  dialogJob = { fields, send, done };
  $("dlg").showModal();
}
$("dlgForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const values = { pin: $("pin").value };
  for (const input of $("dlgFields").querySelectorAll("input, select")) values[input.name] = input.value;
  $("dlgOk").disabled = true;
  const res = await dialogJob.send(values);
  $("dlgOk").disabled = false;
  if (res.ok) {
    $("dlg").close();
    dialogJob.done(res);
    loadOverview();
    loadAlerts();
    fetchMat();
    fetchTimeline();
  } else {
    $("dlgErr").textContent = res.error; // the server's own text, e.g. a wrong PIN
    ($("pinRow").hidden ? $("dlgFields").querySelector("input") : $("pin")).select();
  }
});
$("dlgCancel").addEventListener("click", () => $("dlg").close());

let toastTimer = 0;
function toast(msg) {
  setText($("toast"), msg);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => setText($("toast"), ""), 6000);
}

$("editBtn").addEventListener("click", () => {
  const m = S.mats.find((x) => x.id === S.selected);
  if (!m) return;
  writeDialog({
    title: t("dlgEdit"),
    fields: [
      { key: "name", label: t("fName"), value: m.name }, { key: "room", label: t("fRoom"), value: m.room },
      { key: "seat", label: t("fSeat"), value: m.seat }, { key: "unit", label: t("fUnit"), value: m.unit },
    ],
    send: (v) => send("PUT", "/api/mats/" + encodeURIComponent(m.id) + "/meta", v),
    done: (res) => toast(t("savedBy", { u: res.user })),
  });
});

// ---------- users (PINs are per person; viewing needs no login, changes need an admin's PIN) ----------
const pinFields = () => [
  { key: "pin1", label: t("fNewPin"), type: "password" }, { key: "pin2", label: t("fRepeatPin"), type: "password" },
];
const samePin = (v) => (v.pin1 === v.pin2 ? null : { ok: false, error: t("pinMismatch") });

function firstUserDialog() {
  writeDialog({
    title: t("dlgFirst"), hint: t("firstHint"), noPin: true,
    fields: [{ key: "name", label: t("fName") }, ...pinFields()],
    send: async (v) => samePin(v) || send("POST", "/api/users", { name: v.name, role: "admin", new_pin: v.pin1 }),
    done: (res) => { S.needsAdmin = false; toast(t("userAdded", { n: res.created.name })); },
  });
}

async function renderUsers() {
  let data;
  try { data = await api("/api/users"); } catch (e) { toast(t("netErr")); return false; }
  const list = $("userList");
  list.textContent = "";
  for (const u of data.users) {
    const li = el("li"), acts = el("span", "acts");
    li.append(el("span", u.active ? "who" : "who off",
      u.name + " · " + t(u.role === "admin" ? "roleAdmin" : "roleUser") + (u.active ? "" : " · " + t("userOff"))));
    for (const [key, change] of [[u.active ? "disable" : "enable", { active: !u.active }], ["resetPin", null]]) {
      const b = el("button", "link", t(key));
      b.type = "button";
      b.addEventListener("click", () => writeDialog({
        title: t(change ? (u.active ? "dlgDisable" : "dlgEnable") : "dlgResetPin", { n: u.name }),
        fields: change ? [] : pinFields(), pinLabel: t("adminPin"),
        send: async (v) => (change ? null : samePin(v)) ||
          send("PUT", "/api/users/" + u.id, Object.assign({ pin: v.pin }, change || { new_pin: v.pin1 })),
        done: (res) => { renderUsers(); toast(t("userChanged", { u: res.user })); },
      }));
      acts.append(b);
    }
    li.append(acts);
    list.append(li);
  }
  return true;
}

async function openUsers() {
  if (S.needsAdmin) return firstUserDialog();
  if (await renderUsers()) $("usersDlg").showModal();
}

$("userAdd").addEventListener("click", () => writeDialog({
  title: t("dlgAddUser"), pinLabel: t("adminPin"),
  fields: [
    { key: "name", label: t("fName") },
    { key: "role", label: t("fRole"), options: [["user", t("roleUser")], ["admin", t("roleAdmin")]] },
    ...pinFields(),
  ],
  send: async (v) => samePin(v) || send("POST", "/api/users", { pin: v.pin, name: v.name, role: v.role, new_pin: v.pin1 }),
  done: (res) => { renderUsers(); toast(t("userAdded", { n: res.created.name })); },
}));
$("usersClose").addEventListener("click", () => $("usersDlg").close());
$("usersBtn").addEventListener("click", openUsers);

async function checkSetup() { // no users yet: ask for the first admin, once per page load
  const h = await api("/api/health");
  S.needsAdmin = !!h.needs_admin;
  if (S.needsAdmin && !S.setupShown && !$("dlg").open) { S.setupShown = true; firstUserDialog(); }
}

// ---------- help page ----------
function renderHelp() {
  const h = i18n[lang].help_, page = $("help");
  page.textContent = "";
  const top = el("p");
  const back = el("button", "link", "← " + t("back"));
  back.type = "button";
  back.addEventListener("click", () => showHelp(false));
  top.append(back);
  page.append(top, el("h1", "", h.title));
  page.append(el("h2", "", h.colours[0]));
  for (const [cls, name, text] of h.colours[1]) {
    const row = el("div", "legend-row"), chip = el("span", "chip status " + cls, name);
    row.append(chip, document.createTextNode(text));
    page.append(row);
  }
  const list = (key, tag) => {
    page.append(el("h2", "", h[key][0]));
    const ul = el(tag);
    for (const item of h[key][1]) ul.append(el("li", "", item));
    page.append(ul);
  };
  list("alert", "ol");
  list("map", "ul");
  list("note", "ul");
}
function showHelp(on) {
  $("dash").hidden = on;
  $("help").hidden = !on;
  window.scrollTo(0, 0);
}

// ---------- language, theme ----------
function applyLang() {
  document.documentElement.lang = lang === "en" ? "en" : "nb";
  for (const n of document.querySelectorAll("[data-i]")) n.textContent = t(n.dataset.i);
  for (const n of document.querySelectorAll("[data-i-ph]")) n.placeholder = t(n.dataset.iPh);
  for (const n of document.querySelectorAll("[data-i-label]")) n.setAttribute("aria-label", t(n.dataset.iLabel));
  setText($("langBtn"), t("langBtn"));
  setText($("foot"), t("foot"));
  $("bellpanel").setAttribute("aria-label", t("alerts"));
  for (const r of rows.values()) r.row.remove();
  rows.clear();
  applyTheme(document.documentElement.dataset.theme, false);
  renderHelp();
  renderList();
  renderBell();
  renderPanel();
}

function applyTheme(mode, save = true) {
  const dark = mode === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  if (save) store.set("theme", dark ? "dark" : "light");
  for (const [id, kind] of [["logo", "lockup"], ["logoMark", "mark"]]) $(id).src = `img/logo_${kind}_${dark ? "dark" : "light"}.png`;
  document.querySelector('meta[name="theme-color"]').content = cssVar("--brandbar") || "#FFFFFF";
  setText($("themeBtn"), t(dark ? "light" : "dark"));
  const snap = S.mat && S.mat.snapshot;
  if (snap && save) renderPanel();
}

// ---------- wiring ----------
$("sort").value = SORTS[S.sort] ? S.sort : "risk";
$("sort").addEventListener("change", () => { S.sort = $("sort").value; store.set("sort", S.sort); renderList(); });
$("unit").addEventListener("change", () => { S.unit = $("unit").value; store.set("unit", S.unit); renderList(); });
$("search").addEventListener("input", () => { S.q = $("search").value; renderList(); });
$("bell").addEventListener("click", () => setBell(!S.bellOpen));
$("helpBtn").addEventListener("click", () => showHelp($("help").hidden));
$("langBtn").addEventListener("click", () => { lang = lang === "nb" ? "en" : "nb"; store.set("lang", lang); applyLang(); });
$("themeBtn").addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
$("toList").addEventListener("click", () => $("list").scrollIntoView());
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && S.bellOpen) { setBell(false); $("bell").focus(); } });
document.addEventListener("click", (ev) => {
  if (S.bellOpen && !ev.target.closest("#bellpanel, #bell, dialog")) setBell(false);
});
window.addEventListener("resize", () => { const r = rows.get(S.selected); if (r && !r.detail.hidden) drawTimeline(r.tlHost); });

function setLost(lost) {
  S.lost = lost;
  document.body.classList.toggle("lost", lost);
  $("banner").hidden = !lost;
  setText($("banner"), t("lostServer"));
}

async function loadOverview() {
  try {
    const d = await api("/api/overview");
    S.mats = d.mats;
    S.openAlerts = d.open_alerts;
    S.offset = d.server_time - Date.now() / 1000;
    setLost(false);
  } catch (e) {
    setLost(true); // keep the last rows, but they no longer look healthy
  }
  renderUnits();
  renderList();
  renderBell();
  renderPanel();
  if (S.bellOpen) loadAlerts();
}

async function loadAlerts() {
  try { S.alerts = (await api("/api/alerts")).alerts; renderBell(); } catch (e) { /* the banner already says so */ }
}

async function loadTheme() { // colour ramp shared with the desktop app; the built-in one stays if this fails
  try {
    const stops = (await api("/api/theme")).heatmap_stops;
    if (Array.isArray(stops) && stops.length > 1) S.ramp = stops.map(([v, c]) => [Number(v), c.map(Number)]);
    const g = S.ramp.map(([v, c]) => `rgb(${c[0]},${c[1]},${c[2]}) ${Math.round(v * 100)}%`).join(",");
    $("ramp").style.background = `linear-gradient(90deg, ${g})`;
    renderPanel();
  } catch (e) { /* fallback ramp */ }
}

applyLang();
$("ramp").style.background = "linear-gradient(90deg," + S.ramp.map(([v, c]) => `rgb(${c.join(",")}) ${Math.round(v * 100)}%`).join(",") + ")";
loadTheme();
every(2000, loadOverview);
every(1000, fetchMat);
every(5000, fetchTimeline);
every(10000, checkSetup);
