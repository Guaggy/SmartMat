"""End-to-end check of the whole server pipeline over a real MQTT broker (works on Windows, Linux and macOS).

It starts its own local broker (amqtt) and a SmartMat server in a temporary folder, publishes demo mats like the
ESP32 boards do, and checks what the dashboard API shows: discovery, going offline and alerts, alerts across a server
restart, removing and restoring a mat, a broker restart, garbage on the topics, the web server under abuse, a
risk alert, and mats of other sizes. Nothing in your data folder or config.py is touched.

    pip install amqtt psutil            # once (psutil is optional: it only adds the cpu / memory checks)
    python tools/e2e_check.py           # about 6 minutes; add --quick to skip the one-minute memory watch

Needs the MQTT port 1883 on this computer to be free (stop Mosquitto first if it runs here).
"""

import argparse
import asyncio
import concurrent.futures
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
PORT, BROKER = 8771, 1883
BASE = f"http://127.0.0.1:{PORT}"
ADMIN, NURSE = "1234", "5678"
procs, results = {}, []


# ---------------------------------------------------------------- a tiny local broker (python tools/e2e_check.py --broker)

def run_broker():
    import logging
    from amqtt.broker import Broker
    config = {"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{BROKER}"}}, "sys_interval": 0,
              "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]}, "topic-check": {"enabled": False}}
    logging.basicConfig(level=logging.ERROR)

    async def main():
        await Broker(config).start()
        await asyncio.Event().wait()

    asyncio.run(main())


# ---------------------------------------------------------------- helpers

def check(label, ok, detail=""):
    results.append((label, bool(ok)))
    print(("PASS " if ok else "FAIL ") + label + (f"  [{detail}]" if detail and not ok else ""), flush=True)
    return ok


def info(text):
    print("     " + text, flush=True)


def http(path, method="GET", body=None, raw=None, timeout=10):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    request = urllib.request.Request(BASE + path, method=method, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return response.status, (json.loads(payload) if payload[:1] in (b"{", b"[") else payload)
    except urllib.error.HTTPError as error:
        payload = error.read()
        try:
            return error.code, json.loads(payload)
        except ValueError:
            return error.code, payload


def wait(condition, seconds, step=0.5):
    end = time.time() + seconds
    while time.time() < end:
        try:
            if condition():
                return True
        except Exception:
            pass
        time.sleep(step)
    return False


def mats():
    return {m["id"]: m for m in http("/api/overview")[1]["mats"]}


def alerts():
    return http("/api/alerts")[1]["alerts"]


def spawn(*args, log=None):
    # the check's own broker, whatever broker this PC's saved settings or config.py name
    env = dict(os.environ, PYTHONPATH=str(APP), PYTHONUNBUFFERED="1", SMARTMAT_MQTT_HOST="127.0.0.1",
               SMARTMAT_MQTT_PORT=str(BROKER), SMARTMAT_MQTT_USER="", SMARTMAT_MQTT_PASSWORD="")
    return subprocess.Popen([sys.executable, *args], cwd=APP, env=env, stdout=log or subprocess.DEVNULL, stderr=subprocess.STDOUT if log else subprocess.DEVNULL)


def start_broker():
    procs["broker"] = spawn(str(Path(__file__).resolve()), "--broker")
    time.sleep(3)


def start_server(data, log):
    procs["server"] = spawn("-m", "server", "--port", str(PORT), "--data-dir", str(data), *EXTRA_SERVER_ARGS, log=log)
    return wait(lambda: http("/api/health")[0] == 200, 40)


def stop_server():
    """SIGTERM where there is one (a clean stop), a plain terminate on Windows"""
    proc = procs["server"]
    if os.name == "nt":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(15)
        return True
    except subprocess.TimeoutExpired:
        proc.kill()
        return False


def start_pub(chip):
    procs[chip] = spawn("tools/publish_demo_mat.py", "--chip-id", chip, "--speed", "3")


def blob(rows, cols, peak, cy, cx, sigma):
    return [[peak * math.exp(-(((r - cy) ** 2 + (c - cx) ** 2) / (2 * sigma ** 2))) for c in range(cols)] for r in range(rows)]


EXTRA_SERVER_ARGS = []


# ---------------------------------------------------------------- the checks

def part_mqtt(data, log, quick):
    import paho.mqtt.client as mqtt
    try:
        import psutil
    except ImportError:
        psutil = None

    print("\n== 1. discovery and live data over MQTT")
    start_pub("demo-a")
    start_pub("demo-b")
    check("both mats appear and are online", wait(lambda: {"demo-a", "demo-b"} <= set(mats()) and all(mats()[c]["online"] for c in ("demo-a", "demo-b")), 40), mats())
    detail = http("/api/mats/demo-a")[1]
    grid = (detail.get("snapshot") or {}).get("grid")
    check("mat detail has a 20x20 grid in kPa", bool(grid) and len(grid) == 20 and len(grid[0]) == 20 and detail["snapshot"]["unit"] == "kPa")
    check("demo mats are marked demo", mats()["demo-a"]["demo"] is True)

    print("\n== 2. admin and runtime settings")
    check("first admin can be created", http("/api/users", "POST", {"name": "Admin", "role": "admin", "new_pin": ADMIN})[0] == 201)
    check("nurse created", http("/api/users", "POST", {"pin": ADMIN, "name": "Kari", "role": "user", "new_pin": NURSE})[0] == 201)
    check("settings applied live", http("/api/settings", "PUT", {"pin": ADMIN, "values": {"stale_after_s": 3, "alert_offline_s": 5}})[0] == 200)

    print("\n== 3. a mat goes silent (killed hard, the broker sends its last will)")
    procs["demo-a"].kill()
    check("demo-a turns offline", wait(lambda: not mats()["demo-a"]["online"] and mats()["demo-a"]["risk"] == "offline", 25), mats().get("demo-a"))
    check("demo-b still online", mats()["demo-b"]["online"])
    check("an offline alert opens for demo-a", wait(lambda: any(a["chip_id"] == "demo-a" and a["kind"] == "offline" and a["state"] == "open" for a in alerts()), 30), alerts())
    check("bell count is 1", http("/api/overview")[1]["open_alerts"] == 1)

    print("\n== 4. it comes back: the alert clears")
    start_pub("demo-a")
    check("demo-a online again", wait(lambda: mats()["demo-a"]["online"], 40))
    check("the alert has cleared", wait(lambda: http("/api/overview")[1]["open_alerts"] == 0, 20))

    print("\n== 5. an open alert survives a server restart")
    procs["demo-a"].kill()
    check("alert opens again", wait(lambda: any(a["chip_id"] == "demo-a" and a["state"] == "open" for a in alerts()), 35), alerts())
    before = [a for a in alerts() if a["chip_id"] == "demo-a" and a["state"] == "open"]
    check("server stops" + (" cleanly on SIGTERM" if os.name != "nt" else " (terminated: Windows has no SIGTERM, this is also a crash test)"), stop_server())
    check("server starts again on the same data", start_server(data, log))
    check("mats are rediscovered", wait(lambda: "demo-a" in mats() and "demo-b" in mats() and mats()["demo-b"]["online"], 40), mats())
    after = [a for a in alerts() if a["chip_id"] == "demo-a" and a["state"] == "open"]
    check("same alert id still open, not duplicated", len(after) == 1 and after[0]["id"] == before[0]["id"], (before, after))
    check("the users survived", len(http("/api/users")[1]["users"]) == 2)

    print("\n== 6. remove and restore a retired mat")
    check("a live mat cannot be removed", http("/api/mats/demo-b/hide", "POST", {"pin": ADMIN})[0] == 409)
    check("a nurse cannot remove", http("/api/mats/demo-a/hide", "POST", {"pin": NURSE})[0] == 403)
    check("an admin removes the offline mat", http("/api/mats/demo-a/hide", "POST", {"pin": ADMIN})[0] == 200)
    check("it is gone from the list and its alert closed", "demo-a" not in mats() and http("/api/overview")[1]["open_alerts"] == 0)
    stop_server()
    start_server(data, log)
    time.sleep(8)
    check("still removed after a restart", "demo-a" not in mats(), list(mats()))
    check("restore", http("/api/mats/demo-a/show", "POST", {"pin": ADMIN})[0] == 200)
    check("it reappears from the broker's retained meta", wait(lambda: "demo-a" in mats(), 25), list(mats()))

    print("\n== 7. broker restart (connections drop, retained messages are lost)")
    procs["broker"].kill()
    time.sleep(4)
    check("the dashboard still answers with the broker down", http("/api/health")[0] == 200)
    start_broker()
    check("demo-b recovers by itself", wait(lambda: mats()["demo-b"]["online"], 70), mats().get("demo-b"))

    print("\n== 8. garbage on the MQTT topics")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="evil")
    client.connect("127.0.0.1", BROKER)
    client.loop_start()
    garbage = [("smartmat/evil1/meta", "evil1,20,20,abc"), ("smartmat/evil2/meta", "evil2,0,0,255"), ("smartmat/evil3/meta", "evil3,9999,9999,255"),
               ("smartmat/ev il/meta", "ev il,20,20"), ("smartmat/evil5/meta", "evil5,20,20,255,MODEL,-1,5"), ("smartmat/evil6/meta", "x" * 100000),
               ("smartmat/demo-b/frame", "1,2,3"), ("smartmat/demo-b/frame", "a,b,c"), ("smartmat/demo-b/frame", "9" * 500000),
               ("smartmat/demo-b/frame", ",".join(["999999"] * 400)), ("smartmat/demo-b/frame", ",".join(["-5"] * 400)), ("smartmat/demo-b/frame", "nan," * 399 + "1"),
               ("smartmat/demo-b/status", "maybe"), ("smartmat/evil7/status", "online")]
    for topic, payload in garbage:
        client.publish(topic, payload.encode(), qos=0, retain=topic.endswith("/meta"))
    client.publish("smartmat/demo-b/frame", bytes([0xff, 0xfe, 0x00, 0x80]), qos=0)
    time.sleep(5)
    check("server is healthy", http("/api/health")[0] == 200)
    check("no mat was created from bad meta", not any(i.startswith("evil") for i in mats()), list(mats()))
    check("demo-b still delivers a good grid", wait(lambda: (http("/api/mats/demo-b")[1].get("snapshot") or {}).get("grid") is not None, 15))
    client.loop_stop()
    client.disconnect()

    print("\n== 9. the web server under abuse")
    check("static page", http("/")[0] == 200)
    for path in ("/config.py", "/../config.py", "/static/../config.py", "/..%2fconfig.py", "/%2e%2e/config.py", "/static/..%2f..%2fconfig.py",
                 "/api/../config.py", "/..%5cconfig.py", "/static/..%5c..%5cconfig.py", "/__main__.py", "/store.py", "/smartmat.db"):
        status, payload = http(path)
        leaked = isinstance(payload, bytes) and (b"broker_host" in payload or b"SQLite" in payload or b"import " in payload[:300])
        check(f"{path} does not leak files", not leaked and status in (404, 400, 301, 308), (status, payload[:60] if isinstance(payload, bytes) else payload))
    check("invalid JSON body is a 400", http("/api/settings", "PUT", raw=b"{nope")[0] == 400)
    check("a 5 MB body is refused or 400", http("/api/settings", "PUT", raw=b"{" + b"a" * 5_000_000 + b"}")[0] in (400, 401, 413))
    check("odd hours values are handled", all(http(f"/api/mats/demo-b/timeline?hours={h}")[0] in (200, 400) for h in ("nan", "-5", "1e99", "abc", "")))
    check("an unknown mat is 404", http("/api/mats/nope")[0] == 404)
    check("a SQL-looking id is just unknown", http("/api/mats/x'%20OR%20'1'='1")[0] == 404)
    check("a wrong PIN is 403", http("/api/settings", "PUT", {"pin": "0000", "values": {"near_percent": 70}})[0] == 403)
    check("a wrong HTTP method is 405", http("/api/overview", "DELETE")[0] == 405)
    check("script text in a mat name is stored as text", http("/api/mats/demo-b/meta", "PUT", {"pin": ADMIN, "name": "<img src=x onerror=alert(1)>", "room": "1"})[0] == 200)
    check("the name comes back verbatim (the page uses textContent)", mats()["demo-b"]["name"] == "<img src=x onerror=alert(1)>")
    http("/api/mats/demo-b/meta", "PUT", {"pin": ADMIN, "name": "Demo B"})

    print("\n== 10. parallel load while frames stream")
    proc = psutil.Process(procs["server"].pid) if psutil else None
    cpu0, t0 = (sum(proc.cpu_times()[:2]) if proc else 0), time.time()
    with concurrent.futures.ThreadPoolExecutor(30) as pool:
        futures = [pool.submit(http, p) for _ in range(40) for p in ("/api/overview", "/api/mats/demo-b", "/api/mats/demo-b/timeline?hours=5", "/api/alerts", "/api/settings")]
        statuses = [f.result()[0] for f in futures]
    check("200 parallel requests all answered 200", statuses.count(200) == len(statuses), {s: statuses.count(s) for s in set(statuses)})
    time.sleep(10)
    if proc:
        cpu = (sum(proc.cpu_times()[:2]) - cpu0) / (time.time() - t0) * 100
        info(f"server cpu {cpu:.0f} % of one core, memory {proc.memory_info().rss / 1048576:.0f} MB")
        check("cpu stays reasonable with 2 mats and load", cpu < 150, cpu)
        if not quick:
            m0 = proc.memory_info().rss / 1048576
            time.sleep(60)
            m1 = proc.memory_info().rss / 1048576
            info(f"memory over a minute: {m0:.0f} -> {m1:.0f} MB")
            check("memory does not grow much in a minute", m1 - m0 < 30, (m0, m1))
    else:
        info("psutil is not installed: cpu and memory checks skipped")
    check("the database is not huge", sum(f.stat().st_size for f in data.glob("smartmat.db*")) < 20_000_000)

    print("\n== 11. mats of other sizes (resistive board 3-field meta, big, non-square, tiny, single cell)")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sizes")
    client.connect("127.0.0.1", BROKER)
    client.loop_start()
    cases = [("res-16x16", 16, 16, None, 1000), ("big-32x32", 32, 32, 255, 255), ("flat-12x30", 12, 30, 255, 255), ("tiny-4x4", 4, 4, 255, 255), ("one-1x1", 1, 1, 255, 255)]
    for chip, rows, cols, vmax_field, vmax in cases:
        client.publish(f"smartmat/{chip}/meta", f"{chip},{rows},{cols}" + (f",{vmax_field}" if vmax_field else ""), qos=1, retain=True)
        client.publish(f"smartmat/{chip}/status", "online", qos=1, retain=True)
    http("/api/settings", "PUT", {"pin": ADMIN, "values": {"stale_after_s": None, "alert_offline_s": None}})   # back to the defaults
    time.sleep(5)
    for _ in range(20):   # all mats at once, so none of them goes quiet while the others are sent
        for chip, rows, cols, _, vmax in cases:
            grid = blob(rows, cols, vmax * 0.5, rows * 0.4, cols * 0.5, max(1.0, min(rows, cols) / 5))
            client.publish(f"smartmat/{chip}/frame", ",".join(str(int(v)) for row in grid for v in row), qos=0)
        time.sleep(0.12)
    for chip, rows, cols, _, _ in cases:
        ok = check(f"{chip} is discovered and online", wait(lambda: mats().get(chip, {}).get("online"), 25), mats().get(chip))
        if ok:
            snap = http(f"/api/mats/{chip}")[1].get("snapshot")
            check(f"{chip} grid is {rows}x{cols}", bool(snap) and snap["grid"] is not None and len(snap["grid"]) == rows and len(snap["grid"][0]) == cols)
    client.publish("smartmat/flat-12x30/meta", "flat-12x30,10,10,255", qos=1, retain=True)
    time.sleep(6)
    for _ in range(15):
        client.publish("smartmat/flat-12x30/frame", ",".join(str(int(v)) for row in blob(10, 10, 100, 4, 5, 2) for v in row), qos=0)
        time.sleep(0.12)
    check("a mat that changes its size follows the new size", wait(lambda: len((http("/api/mats/flat-12x30")[1].get("snapshot") or {}).get("grid") or []) == 10, 25))
    client.publish("smartmat/flat-12x30/frame", ",".join(["5"] * 360), qos=0)   # a frame of the old size
    time.sleep(3)
    check("the server is healthy after a frame of the wrong size", http("/api/health")[0] == 200)
    client.loop_stop()
    client.disconnect()


def part_layers(data, log):
    print("\n== 12. per-mat settings over MQTT: own alert delay, the version on the alert, history, restart, rollback")
    start_pub("lay-a")
    start_pub("lay-b")
    check("both mats online", wait(lambda: all(mats().get(c, {}).get("online") for c in ("lay-a", "lay-b")), 40), {c: mats().get(c) for c in ("lay-a", "lay-b")})
    check("site layer: offline alert after 40 s", http("/api/settings", "PUT", {"pin": ADMIN, "values": {"alert_offline_s": 40}, "reason": "quiet ward"})[0] == 200)
    check("a nurse cannot set a mat's own value", http("/api/mats/lay-b/config", "PUT", {"pin": NURSE, "values": {"alert_offline_s": 5}})[0] == 403)
    check("lay-b gets its own 5 s", http("/api/mats/lay-b/config", "PUT", {"pin": ADMIN, "values": {"alert_offline_s": 5}, "reason": "critical chair"})[0] == 200)
    setting = lambda chip, key: next(i for i in http(f"/api/mats/{chip}/config")[1]["settings"] if i["key"] == key)
    check("lay-a inherits the site's 40 s", (setting("lay-a", "alert_offline_s")["value"], setting("lay-a", "alert_offline_s")["source"]) == (40, "site"))
    check("lay-b shows its own 5 s", (setting("lay-b", "alert_offline_s")["value"], setting("lay-b", "alert_offline_s")["source"]) == (5, "mat"))
    check("a value that breaks the threshold order is refused", http("/api/mats/lay-b/config", "PUT", {"pin": ADMIN, "values": {"hotspots.deactivate_kpa": 99}})[0] == 400)
    procs["lay-a"].kill()
    procs["lay-b"].kill()
    check("lay-b raises its offline alert after its own 5 s", wait(lambda: any(a["chip_id"] == "lay-b" and a["state"] == "open" for a in alerts()), 15), alerts())
    check("lay-a, on the site's 40 s, has none yet", not any(a["chip_id"] == "lay-a" for a in alerts()))
    alert = next((a for a in alerts() if a["chip_id"] == "lay-b" and a["state"] == "open"), {})
    import re
    check("the alert says which settings version raised it", re.fullmatch(r"s\d+\.m1", alert.get("config") or "") is not None, alert.get("config"))
    check("server stops", stop_server())
    check("server starts again", start_server(data, log))
    check("the mat's own layer survived the restart", wait(lambda: (setting("lay-b", "alert_offline_s")["value"], setting("lay-b", "alert_offline_s")["source"]) == (5, "mat"), 30))
    kept = [a for a in alerts() if a["chip_id"] == "lay-b" and a["state"] == "open"]
    check("the restored alert keeps its version stamp", len(kept) == 1 and kept[0]["id"] == alert.get("id") and kept[0]["config"] == alert.get("config"), kept)
    history = http("/api/config/history?scope=lay-b")[1]["history"]
    check("history: one version, by Admin, with the reason", [(h["version"], h["user"], h["reason"]) for h in history] == [(1, "Admin", "critical chair")], history)
    check("the site's history has the reason too", any(h["reason"] == "quiet ward" for h in http("/api/config/history")[1]["history"]))
    status, body = http("/api/config/rollback", "POST", {"pin": ADMIN, "scope": "lay-b", "version": 0, "reason": "back to the site"})
    check("rolling lay-b back to version 0 is a new version", status == 200 and body["version"] == 2 and body["changed"] == 1, body)
    check("lay-b inherits the site again", (setting("lay-b", "alert_offline_s")["value"], setting("lay-b", "alert_offline_s")["source"]) == (40, "site"))
    check("the history keeps both versions", [h["version"] for h in http("/api/config/history?scope=lay-b")[1]["history"]] == [2, 1])
    http("/api/settings", "PUT", {"pin": ADMIN, "values": {"alert_offline_s": None}, "reason": "end of the test"})


def part_passport(data, log):
    print("\n== 13. the passport kept on a mat: a new mat brings its calibration, backup and restore over a real broker")
    from matlink.passport_link import PahoTransport, PassportLink
    from processing import passport
    procs["pp-dev"] = spawn("tools/fake_passport_device.py", "--chip-id", "pass-a", "--serial", "SM-0042", "--service-key", "sesame", "--custom", "20x20", log=log)
    time.sleep(2)
    start_pub("pass-a")
    check("the new mat appears", wait(lambda: mats().get("pass-a", {}).get("online"), 40), mats().get("pass-a"))
    events = lambda: [e["kind"] for e in http("/api/mats/pass-a/log")[1].get("events", [])]
    check("it was calibrated from its own passport, without anyone touching it", wait(lambda: "passport adopted" in events(), 20), events())
    status, body = http("/api/mats/pass-a/passport")
    custom = (body.get("slots") or {}).get("custom") or {}
    check("the status shows serial, slot and that it is the calibration in use", status == 200 and body.get("serial") == "SM-0042" and custom.get("same_as_now") is True, body)
    check("a nurse cannot write the passport", http("/api/mats/pass-a/passport/write", "POST", {"pin": NURSE})[0] == 403)
    status, body = http("/api/mats/pass-a/passport/write", "POST", {"pin": ADMIN, "note": "e2e backup"})
    check("an admin writes the custom slot (version 2)", status == 200 and body.get("version") == 2, body)
    transport = PahoTransport("127.0.0.1", BROKER, client_id="e2e-passport-tool")
    transport.wait_connected(10)
    link = PassportLink(transport, 5)
    try:
        document, blob = link.read("pass-a", "custom")
        check("read back over MQTT: the note, the writer and the version", (document["note"], document["written_by"], document["version"]) == ("e2e backup", "Admin", 2), document["note"])
        check("the mat's CRC is the bytes' CRC", (link.summary("pass-a")["custom"] or {}).get("crc") == passport.crc_hex(blob))
        try:
            link.write("pass-a", "factory", passport.encode(passport.build("factory", "SM-0042", "MC266", document["profile"])), "wrong")
            refused = False
        except Exception as error:
            refused = "service key" in str(error)
        check("the factory slot refuses a wrong service key", refused)
        link.write("pass-a", "factory", passport.encode(passport.build("factory", "SM-0042", "MC266", document["profile"])), "sesame")
        check("and takes the right one", link.read("pass-a", "factory")[0]["slot"] == "factory")
    finally:
        link.close()
    status, body = http("/api/mats/pass-a/passport/adopt", "POST", {"pin": ADMIN, "slot": "factory"})
    check("adopting the factory passport works and is logged", status == 200 and events().count("passport adopted") == 2, body)
    procs["pass-a"].kill()
    procs["pp-dev"].kill()


def part_risk(log):
    print("\n== 14. the risk pipeline reaches high and raises an alert (demo mats run faster than real time)")
    stop_server()
    procs["server"] = None
    EXTRA_SERVER_ARGS[:] = ["--demo", "5"]
    data = Path(tempfile.mkdtemp(prefix="smartmat_e2e_risk_"))
    try:
        check("a server with five demo mats starts", start_server(data, log))
        http("/api/users", "POST", {"name": "Admin", "role": "admin", "new_pin": ADMIN})
        time.sleep(10)
        info("risks before: " + str({k: v["risk"] for k, v in mats().items() if k.startswith("demo-") and k[5:].isdigit()}))
        check("sensitive risk settings applied", http("/api/settings", "PUT", {"pin": ADMIN, "values": {"relief_minutes": 10, "near_percent": 50, "alert_high_hold_s": 5}})[0] == 200)
        seen = {}
        got = wait(lambda: seen.update({k: v["risk"] for k, v in mats().items()}) or "high" in seen.values(), 170, 1)
        info("risks now: " + str({k: v for k, v in seen.items() if k[5:].isdigit()}))
        check("at least one demo mat reaches HIGH risk", got, seen)
        check("a high-risk alert is raised", wait(lambda: any(a["kind"] == "high_risk" and a["state"] == "open" for a in alerts()), 45), alerts())
        alert = next((a for a in alerts() if a["kind"] == "high_risk"), None)
        if alert:
            status, body = http(f"/api/alerts/{alert['id']}/ack", "POST", {"pin": ADMIN})
            check("acknowledging it works and names the user", status == 200 and body["user"] == "Admin", body)
            check("a second acknowledge is refused (409)", http(f"/api/alerts/{alert['id']}/ack", "POST", {"pin": ADMIN})[0] == 409)
        row = next((m for m in mats().values() if m["risk"] == "high"), None)
        if row:
            segments = http(f"/api/mats/{row['id']}/timeline?hours=1")[1]["segments"]
            check("the timeline records the high-risk segment", any(s["risk"] == "high" for s in segments), segments[-3:])
    finally:
        stop_server()
        shutil.rmtree(data, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--broker", action="store_true", help="(internal) run only the local test broker")
    parser.add_argument("--quick", action="store_true", help="skip the one-minute memory watch")
    args = parser.parse_args()
    if args.broker:
        return run_broker()
    try:
        import amqtt  # noqa: F401
        import paho.mqtt.client  # noqa: F401
    except ImportError as error:
        sys.exit(f"{error}\nInstall what the check needs: pip install amqtt psutil   (and the app's requirements.txt)")
    import socket
    probe = socket.socket()
    if probe.connect_ex(("127.0.0.1", BROKER)) == 0:
        sys.exit(f"Port {BROKER} is already in use on this computer (Mosquitto?). Stop it for the check, the check starts its own broker.")
    probe.close()

    data = Path(tempfile.mkdtemp(prefix="smartmat_e2e_"))
    log = open(data / "server.log", "w")
    try:
        start_broker()
        if not start_server(data, log):
            check("the server starts", False)
            return
        part_mqtt(data, log, args.quick)
        part_layers(data, log)
        part_passport(data, log)
        part_risk(log)
        log.flush()
        text = (data / "server.log").read_text(errors="replace")
        check("no traceback anywhere in the server log", "Traceback" not in text, text[-600:])
    finally:
        for proc in procs.values():
            try:
                proc and proc.kill()
            except Exception:
                pass
        log.close()
        failed = [label for label, ok in results if not ok]
        print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed   (server log: {data / 'server.log'})")
        for label in failed:
            print("  FAILED:", label)
        shutil.rmtree(data, ignore_errors=True) if not failed else None


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    sys.exit(1 if any(not ok for _, ok in results) else 0)
