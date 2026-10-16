"""Mock SmartMat API for developing the web dashboard without the real server.

Run from the app folder:  python tools/mock_api.py [--port 8000] [--host 127.0.0.1]
Serves server/static/ and fake JSON for the endpoints in design/api-contract.md. Eight fake mats
play the seated part of samples/seat_take1.json (mirrored, shifted and scaled per mat). A write
needs "pin" 1234 (user "Test Nurse") and changes in-memory state only; restart to reset.
"""

import argparse
import json
import random
import sys
import threading
import time
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, request

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
import branding  # noqa: E402  (shared palette and heatmap ramp, single source)

PIN, USER, STALE_AFTER_S, KPA_FULL = "1234", "Test Nurse", 10, 50.0
POSTURES = ["left", "right", "forward", "centred"]

app = Flask(__name__, static_folder=str(APP_DIR / "server" / "static"), static_url_path="")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
LOCK = threading.Lock()
T0 = time.time()

# the seated part of the take: counts 0..1000 -> kPa on the default curve (1000 = 50 kPa)
_frames = np.array([f["raw"] for f in json.load(open(APP_DIR / "samples" / "seat_take1.json"))["frames"]], dtype=float)
FRAMES = _frames[int(np.argmax((_frames > 200).sum(axis=(1, 2)) > 200)):]


def shift(grid, dy, dx):
    out = np.zeros_like(grid)
    h, w = grid.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = grid[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


# tip = seconds in the current position, relief = seconds since relief (None = unknown)
MATS = [
    dict(id="demo-take1", name="Demo seat 1", room="Demo", seat="A", unit="Demo", posture="centred", risk="low", tip=58 * 60, relief=95 * 60, scale=0.6, dx=0, dy=0, mirror=False),
    dict(id="sm-101", name="SmartMat 1", room="101", seat="A", unit="Avd. A", posture="left", risk="high", tip=718, relief=None, scale=1.25, dx=-2, dy=0, mirror=False),
    dict(id="sm-102", name="SmartMat 2", room="102", seat="A", unit="Avd. A", posture="forward", risk="medium", tip=77 * 60, relief=3 * 3600, scale=0.8, dx=0, dy=3, mirror=False),
    dict(id="sm-103", name="SmartMat 3", room="103", seat="B", unit="Avd. A", posture="centred", risk="low", tip=58 * 60, relief=58 * 60, scale=0.55, dx=0, dy=0, mirror=True),
    dict(id="sm-104", name="SmartMat 4", room="104", seat="A", unit="Avd. B", posture="centred", risk="medium", tip=40 * 60, relief=40 * 60, scale=0.8, dx=0, dy=0, mirror=False, offline_for=340),
    dict(id="sm-105", name="SmartMat 5", room="105", seat="A", unit="Avd. B", posture="none", risk="none", tip=173, relief=None, scale=0.0, dx=0, dy=0, mirror=False),
    dict(id="sm-106", name="SmartMat 6", room="106", seat="C", unit="Avd. B", posture="right", risk="low", tip=25 * 60, relief=25 * 60, scale=0.7, dx=2, dy=0, mirror=True, relative=True),
    dict(id="demo-seat2", name="Demo seat 2", room="Demo", seat="B", unit="Demo", posture="forward", risk="medium", tip=31 * 60, relief=None, scale=0.8, dx=0, dy=2, mirror=True),
]
for m in MATS:
    m["demo"] = m["id"].startswith("demo-")
    m["pos_at"] = T0 - m["tip"]
    m["relief_at"] = None if m["relief"] is None else T0 - m["relief"]
    m["offline_since"] = T0 - m["offline_for"] if m.get("offline_for") else None
    m["markers"] = []
BY_ID = {m["id"]: m for m in MATS}


def make_history(m):
    """Segments for the last 6 h: earlier random ones, then the current position up to now."""
    rnd = random.Random(m["id"])
    segs, t = [], m["pos_at"]
    while t > T0 - 6 * 3600:
        length = rnd.choice([12, 25, 40, 55, 70, 100]) * 60
        posture = rnd.choices(POSTURES + ["none"], [3, 3, 2, 3, 1])[0]
        risk = "none" if posture == "none" else ("high" if length >= 90 * 60 else "medium" if length >= 45 * 60 else "low")
        segs.insert(0, dict(t_start=t - length, t_end=t, posture=posture, risk=risk))
        t -= length
        if rnd.random() < 0.15:  # a hole: nothing received
            t -= rnd.choice([8, 15]) * 60
    segs.append(dict(t_start=m["pos_at"], t_end=None, posture=m["posture"], risk=m["risk"]))  # t_end None = until now
    return segs


for m in MATS:
    m["segments"] = make_history(m)
BY_ID["sm-101"]["markers"].append(dict(t=T0 - 3 * 3600, kind="handled", user=USER))

ALERTS = [
    dict(id="a1", chip_id="sm-101", kind="high_risk", t_raised=T0 - 540, state="open", by=None),
    dict(id="a2", chip_id="sm-104", kind="offline", t_raised=T0 - 300, state="open", by=None),
    dict(id="a3", chip_id="sm-102", kind="high_risk", t_raised=T0 - 3 * 3600, state="acknowledged", by=USER),
]


def live_grid(m, now):
    """Current 20x20 grid in kPa (or counts when the mat is 'relative') for a mat."""
    if m["scale"] == 0:
        return np.random.default_rng(int(now)).random((20, 20)) * 0.3  # idle noise
    at = m["offline_since"] or now
    n = len(FRAMES)
    i = int(at * 8 + sum(map(ord, m["id"])) % n) % (2 * n)
    grid = FRAMES[min(i, 2 * n - 1 - i)]  # ping-pong through the take
    if m["mirror"]:
        grid = grid[:, ::-1]
    grid = shift(grid, m["dy"], m["dx"])
    full = 1000.0 if m.get("relative") else KPA_FULL
    return np.minimum(grid * (full / 1000) * m["scale"], full)  # clipped at the sensor limit


def hotspots(grid, now):
    """Connected areas of the highest cells (4-neighbour flood fill)."""
    limit = max(0.75 * grid.max(), 20.0)
    todo = {(r, c) for r, c in zip(*np.nonzero(grid >= limit))}
    out = []
    while todo:
        stack, cells = [todo.pop()], []
        while stack:
            r, c = stack.pop()
            cells.append([int(r), int(c)])
            for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if n in todo:
                    todo.remove(n)
                    stack.append(n)
        out.append(dict(cells=sorted(cells), peak_kpa=round(max(grid[r, c] for r, c in cells), 1)))
    out.sort(key=lambda h: -h["peak_kpa"])
    for i, h in enumerate(out):
        h["id"] = i + 1
        h["active_s"] = round((now - T0) % 300, 1)
        h["persistent"] = h["active_s"] > 120 and i == 0
    return out


def row(m, now):
    offline = m["offline_since"] is not None
    pos_end = m["offline_since"] or now
    return dict(
        id=m["id"], name=m["name"], room=m["room"], seat=m["seat"], unit=m["unit"], demo=m["demo"],
        online=not offline, risk="offline" if offline else m["risk"], posture="none" if offline else m["posture"],
        time_in_position_s=round(pos_end - m["pos_at"]),
        since_relief_s=None if m["relief_at"] is None or offline else round(now - m["relief_at"]),
        saturated_cells=int((live_grid(m, now) >= 0.99 * (1000.0 if m.get("relative") else KPA_FULL)).sum()),
        open_alerts=sum(1 for a in ALERTS if a["chip_id"] == m["id"] and a["state"] == "open"),
    )


def index(name, layer, value, threshold):
    ratio = value / threshold
    return dict(name=name, layer=layer, value=round(value, 1), threshold=threshold, state="over" if ratio >= 1 else "near" if ratio >= 0.8 else "ok")


def snapshot(m, now):
    grid = live_grid(m, now)
    occupied = m["scale"] > 0
    relative = bool(m.get("relative"))
    peak = float(grid.max())
    return dict(
        unit="relative" if relative else "kPa", scale_max=1000.0 if relative else KPA_FULL,
        grid=[[round(float(v), 2) for v in r] for r in grid], occupied=occupied,
        hotspots=hotspots(grid, now) if occupied and not relative else [],
        indices=[index("Peak pressure (kPa)", "pressure", peak, 45.0), index("Time in position (min)", "time", row(m, now)["time_in_position_s"] / 60, 90.0)] if occupied and not relative else [],
        peak_kpa=round(peak, 1) if occupied and not relative else None,
    )


def need_pin():
    """None when the PIN is right, else an error response."""
    body = request.get_json(silent=True) or {}
    if str(body.get("pin", "")) != PIN:
        return jsonify(error="Wrong PIN"), 403
    return None


def handled(alert):
    BY_ID[alert["chip_id"]]["markers"].append(dict(t=time.time(), kind="handled", user=USER))


@app.route("/")
def home():
    return app.send_static_file("index.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True, version="mock")


@app.get("/api/theme")
def theme():
    return jsonify(light=branding.PALETTE_LIGHT, dark=branding.PALETTE_DARK, heatmap_stops=[[t, list(c)] for t, c in branding.HEATMAP_STOPS])


@app.get("/api/overview")
def overview():
    now = time.time()
    with LOCK:
        mats = [row(m, now) for m in MATS]
    return jsonify(mats=mats, open_alerts=sum(a["state"] == "open" for a in ALERTS), server_time=now)


@app.get("/api/mats/<mat_id>")
def one_mat(mat_id):
    now = time.time()
    with LOCK:
        m = BY_ID.get(mat_id)
        if m is None:
            return jsonify(error="unknown mat"), 404
        age = round(now - m["offline_since"], 1) if m["offline_since"] else round(random.random() * 0.8, 1)
        return jsonify(dict(row(m, now), snapshot=snapshot(m, now), age_s=age, stale=age > STALE_AFTER_S))


@app.get("/api/mats/<mat_id>/timeline")
def timeline(mat_id):
    now = time.time()
    hours = request.args.get("hours", 5, type=float)
    with LOCK:
        m = BY_ID.get(mat_id)
        if m is None:
            return jsonify(error="unknown mat"), 404
        end = m["offline_since"] or now
        segs = [dict(s, t_end=s["t_end"] or end) for s in m["segments"]]
        segs = [dict(s, t_start=max(s["t_start"], now - hours * 3600)) for s in segs if s["t_end"] > now - hours * 3600]
        return jsonify(segments=[{k: round(v) if k.startswith("t_") else v for k, v in s.items()} for s in segs],
                       markers=[dict(mk, t=round(mk["t"])) for mk in m["markers"] if mk["t"] > now - hours * 3600])


@app.get("/api/alerts")
def alerts():
    with LOCK:
        return jsonify(alerts=[dict(a, name=BY_ID[a["chip_id"]]["name"], room=BY_ID[a["chip_id"]]["room"], t_raised=round(a["t_raised"])) for a in ALERTS])


def handle_alert(alert_id, new_state):
    bad = need_pin()
    if bad:
        return bad
    with LOCK:
        alert = next((a for a in ALERTS if a["id"] == alert_id), None)
        if alert is None:
            return jsonify(error="unknown alert"), 404
        if alert["state"] != "open":
            return jsonify(error="Alert already handled by " + str(alert["by"])), 409
        alert.update(state=new_state, by=USER)
        handled(alert)
    return jsonify(ok=True, user=USER)


@app.post("/api/alerts/<alert_id>/ack")
def ack(alert_id):
    return handle_alert(alert_id, "acknowledged")


@app.post("/api/alerts/<alert_id>/ignore")
def ignore(alert_id):
    return handle_alert(alert_id, "ignored")


@app.put("/api/mats/<mat_id>/meta")
def meta(mat_id):
    bad = need_pin()
    if bad:
        return bad
    body = request.get_json(silent=True) or {}
    with LOCK:
        m = BY_ID.get(mat_id)
        if m is None:
            return jsonify(error="unknown mat"), 404
        if not str(body.get("name", m["name"])).strip():
            return jsonify(error="Name cannot be empty"), 400
        for key in ("name", "room", "seat", "unit"):
            if key in body:
                m[key] = str(body[key]).strip()[:40]
    return jsonify(ok=True, user=USER)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    print(f"Mock SmartMat API on http://{args.host}:{args.port}/  (PIN {PIN})")
    app.run(host=args.host, port=args.port, threaded=True)
