"""SmartMat server: `python -m server [--demo [N]] [--port P] [--data-dir DIR]`.

Every mat on the MQTT broker gets its own MatEngine; USB mats in SERVER_SERIAL_PORTS are read here and
republished to MQTT (same topics as the ESP32 boards) so desktops see them as MQTT mats. A pump feeds the
engines a few frames a second; a 1 s tick writes the timeline, raises/clears alerts and logs them.
"""

import paths  # noqa: F401 - must run first: frozen builds load config.py from paths.APP_DIR

import argparse
import bisect
import json
import signal
import threading
import time
from pathlib import Path

import numpy as np
from werkzeug.serving import make_server

import app_settings
import config
import general
from processing import calibration
from processing.calibration import IndividualCalibration, UniformCalibration, load_profile
from server.alerts import AlertManager
from server.app import DEMO_PREFIX, create_app
from server.engine import MatEngine, grid_shape
from server.push import PushSender
from server.settings import SITE, Settings
from server.store import Store

PUMP_S = 0.25   # ponytail: each mat is analysed at most 4 frames/s; the per-cell calibration loop costs ~13 ms a frame
TICK_S = 1.0
PURGE_EVERY_S = 3600
OPEN_RETRY_S = 10
REPORT_EVERY_S = 60   # a repeating fault of one mat is printed this often at most
CLOCK_JUMP_S = 30     # ticks further apart than this (or going backwards) mean the clock jumped or the loop stalled
SAMPLE = paths.resource_path("samples/seat_take1.json")
DEMO_SPEEDS = (1, 3, 5, 2, 4)  # demo clock runs this many times faster (keeps a frame step under TEMPORAL_MAX_GAP_S)
DEMO_SHIFTS = ((0, 0), (0, -4), (0, 4), (4, 0), (0, 0))  # (rows, cols) the load is moved: centred, left, right, forward


def shifted(grid, rows=0, cols=0):
    """The grid moved by whole cells, empty (0) where nothing moved in"""
    out = np.zeros_like(grid)
    h, w = grid.shape
    out[max(rows, 0):h + min(rows, 0), max(cols, 0):w + min(cols, 0)] =         grid[max(-rows, 0):h + min(-rows, 0), max(-cols, 0):w + min(-cols, 0)]
    return out


class DemoMat:
    """Replays the seat recording: once from `offset_s`, then the seated part in a loop, on a clock `speed` x fast;
    optionally mirrored left-right and moved by `shift` (rows, cols)"""

    def __init__(self, frames, offset_s=0.0, mirror=False, speed=1, shift=(0, 0), wall=time.time):
        self.grids = [shifted(np.fliplr(grid) if mirror else grid, *shift) for grid, _ in frames]
        start = frames[0][1]
        self.times = [t - start for _, t in frames]
        seated = next((i for i, g in enumerate(self.grids) if (g > 50).sum() > 100), 0)
        self.seated_t = self.times[seated]
        self.offset_s, self.speed, self.wall = offset_s, speed, wall
        self.t0 = wall()

    def clock(self):
        return self.t0 + (self.wall() - self.t0) * self.speed

    def take(self):
        t = self.clock()
        position = self.offset_s + t - self.t0
        end = self.times[-1]
        if position > end:
            position = self.seated_t + (position - end) % (end - self.seated_t)
        return self.grids[max(0, bisect.bisect_right(self.times, position) - 1)], t


def demo_profile(rows, cols):
    """The default linear curve as one uniform curve: same kPa, but vectorised (demo mats run many at once)"""
    with grid_shape(rows, cols):
        uniform = UniformCalibration()
        uniform.add_point(config.DEFAULT_PRESSURE_CALIBRATION_RAW_MAX, config.DEFAULT_PRESSURE_CALIBRATION_KPA)
        return {"format": calibration.PROFILE_FORMAT, "grid_shape": [rows, cols], "baseline": None,
                "orientation": {"rotation": 0, "mirror_h": False, "mirror_v": False}, "active": "uniform",
                "individual": IndividualCalibration().to_dict(), "uniform": uniform.to_dict()}


def load_frames(path=SAMPLE):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows, cols = data["grid_shape"]
    return [(np.asarray(f["raw"], dtype=float).reshape(rows, cols), f["timestamp"]) for f in data["frames"]]


class SerialBridge:
    """A USB mat owned by the server: frames go to its engine and, as raw units, to MQTT"""

    def __init__(self, port, profile):
        from sources.serial_source import SerialSource
        import paho.mqtt.client as mqtt
        self.source = SerialSource(port, profile)
        self.chip_id = "usb" + "".join(ch for ch in port if ch.isalnum())  # parse_meta wants an alphanumeric id
        self.latest = general.LatestFrame()
        self._running = False
        rows, cols = self.source.shape
        meta = f"{self.chip_id},{rows},{cols},{self.source.value_max}"
        if self.source.model and self.source.default_size_mm:
            meta += f",{self.source.model},{self.source.default_size_mm[0]:g},{self.source.default_size_mm[1]:g}"
        self._meta = meta
        self._topic = f"smartmat/{self.chip_id}"
        settings = app_settings.effective_mqtt()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"smartmat-server-{self.chip_id}")
        if settings["username"]:
            self._client.username_pw_set(settings["username"], settings["password"])
        self._client.will_set(f"{self._topic}/status", "offline", retain=True)
        self._client.on_connect = self._on_connect
        self._settings = settings

    def _on_connect(self, client, *_):
        client.publish(f"{self._topic}/status", "online", retain=True)
        client.publish(f"{self._topic}/meta", self._meta, retain=True)  # retained, like the ESP32 boards

    def start(self):
        self.source.start()
        self._client.connect_async(self._settings["host"], self._settings["port"])
        self._client.loop_start()
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self._running:
            grid = self.source.latest.take()
            if grid is not None:
                self.latest.set(grid)
                raw = np.rint(grid * self.source.value_max / config.VALUE_MAX_DEFAULT).astype(int)
                self._client.publish(f"{self._topic}/frame", ",".join(map(str, raw.ravel())), retain=False)
            time.sleep(0.02)

    def take(self):
        grid = self.latest.take()
        return None if grid is None else (grid, time.time())

    def stop(self):
        self._running = False
        self.source.stop()
        self._client.publish(f"{self._topic}/status", "offline", retain=True)
        self._client.loop_stop()
        self._client.disconnect()


class MqttMat:
    """One broker mat, streamed with its own MqttSource"""

    def __init__(self, source):
        self.source = source

    def take(self):
        grid = self.source.latest.take()
        return None if grid is None else (grid, time.time())

    def stop(self):
        self.source.stop()


class Server:
    def __init__(self, store, alerts, demo=0, serial_ports=(), use_mqtt=True, pusher=None, settings=None):
        self.store, self.alerts = store, alerts
        self.settings = settings if settings is not None else Settings(store)
        self.pusher = pusher if pusher is not None else PushSender(store, enabled=self.settings.get("push_enabled"))
        self.engines = {}   # chip_id -> MatEngine (read by the web app)
        self.feeds = {}     # chip_id -> DemoMat / MqttMat / SerialBridge
        self._opening = {}  # chip_id -> time an MQTT mat was last tried
        self._stop = threading.Event()
        self._threads = []
        self._reported = {}   # (chip_id, place) -> when a fault was last printed
        self._last_tick = None
        self.hidden = store.hidden_mats()   # retired mats an admin removed: not read, not listed
        self.discovery = None
        if demo:
            frames = load_frames()
            rows, cols = frames[0][0].shape
            for index in range(demo):
                chip_id = f"{DEMO_PREFIX}{index + 1}"
                feed = DemoMat(frames, offset_s=7.0 * index, mirror=index % 2 == 1,
                               speed=DEMO_SPEEDS[index % len(DEMO_SPEEDS)],
                               shift=DEMO_SHIFTS[index % len(DEMO_SHIFTS)])
                self._add(chip_id, MatEngine(chip_id, rows, cols, profile=demo_profile(rows, cols)), feed)
                self.engines[chip_id].clock = feed.clock
        for port, profile in serial_ports:
            try:
                bridge = SerialBridge(port, profile)
                bridge.start()
            except Exception as error:  # a missing port must not stop the server
                print(f"Serial mat on {port} not started: {error}")
                continue
            rows, cols = bridge.source.shape
            self._add(bridge.chip_id, MatEngine(bridge.chip_id, rows, cols, bridge.source.value_max,
                                                load_profile(bridge.chip_id), bridge.source.default_size_mm), bridge)
        if use_mqtt:
            try:  # never blocks: paho keeps retrying in its thread while there is no broker
                from sources.mqtt_source import MqttSource
                self.discovery = MqttSource(client_id="smartmat-server-discovery")
                self.discovery.start()
            except Exception as error:
                print(f"MQTT not started: {type(error).__name__}: {error}")
                self.discovery = None
        self.settings.listen(self._apply_settings, call=False)  # a change in the dashboard applies at once

    def _add(self, chip_id, engine, feed):
        self._configure(chip_id, engine)
        self.engines[chip_id], self.feeds[chip_id] = engine, feed

    def _configure(self, chip_id, engine):
        """This mat's settings: its own layer on top of the site layer on top of the factory values"""
        values = self.settings.resolved(chip_id)
        engine.configure(values)
        self.alerts.set_holds(chip_id, values["alert_high_hold_s"], values["alert_offline_s"])

    def _apply_settings(self, scope):
        """A layer changed: "site" reaches every mat, a mat's id only that mat"""
        site = self.settings.resolved()
        if scope == SITE:
            self.alerts.holds = {"high_risk": site["alert_high_hold_s"], "offline": site["alert_offline_s"]}
            self.pusher.enabled = site["push_enabled"]
        for chip_id, engine in list(self.engines.items()):
            if scope in (SITE, chip_id):
                self._configure(chip_id, engine)

    # ---- MQTT mats come and go

    def _discover(self, now):
        if self.discovery is None:
            return
        for chip_id, shape in list(self.discovery.mats.items()):
            if chip_id in self.hidden:
                continue
            engine = self.engines.get(chip_id)
            if engine is not None:
                engine.status = self.discovery.status.get(chip_id)
                if engine.shape != tuple(shape) and isinstance(self.feeds.get(chip_id), MqttMat):
                    self._add(chip_id, self._mqtt_engine(chip_id), self.feeds[chip_id])  # firmware changed size
            elif now - self._opening.get(chip_id, -OPEN_RETRY_S) >= OPEN_RETRY_S:
                self._opening[chip_id] = now
                threading.Thread(target=self._open_mqtt, args=(chip_id,), daemon=True).start()

    def _mqtt_engine(self, chip_id):
        rows, cols = self.discovery.mats[chip_id]
        preset = self.discovery.presets.get(chip_id, (None, None))
        return MatEngine(chip_id, rows, cols, self.discovery.value_maxes.get(chip_id, config.VALUE_MAX_DEFAULT),
                         load_profile(chip_id), preset[1])

    def _open_mqtt(self, chip_id):
        from sources.mqtt_source import MqttSource
        source = MqttSource(chip_id, client_id=f"smartmat-server-{chip_id}")
        try:
            source.start()  # blocks until the mat's meta arrives (a few seconds at most)
        except Exception as error:
            print(f"Mat {chip_id} not opened: {error}")
            return
        if self._stop.is_set() or chip_id in self.hidden:  # shut down, or removed while it was opening
            source.stop()
            return
        self._add(chip_id, self._mqtt_engine(chip_id), MqttMat(source))
        self.store.log(time.time(), "mat connected", chip_id)

    # ---- removing and restoring a retired mat (admin, from the dashboard)

    def hide(self, chip_id, now):
        """Stop reading a mat, close its open alerts and keep it out of the lists. ValueError for a mat that is online
        (only retired ones are removed; a live mat would just come back with its next frame)."""
        engine = self.engines.get(chip_id)
        if engine is not None and engine.online(engine.clock()):
            raise ValueError("Only a mat that is offline can be removed")
        self.store.hide_mat(chip_id, now)
        self.hidden.add(chip_id)
        feed = self.feeds.pop(chip_id, None)
        self.engines.pop(chip_id, None)
        if feed is not None and hasattr(feed, "stop"):
            feed.stop()
        for alert in self.alerts.forget(chip_id, now):
            self.store.log(now, "alert cleared", chip_id, None, {"alert": alert["id"], "kind": alert["kind"]})

    def show(self, chip_id):
        """Bring a removed mat back: the next discovery round opens it again if the broker still has it"""
        self.hidden.discard(chip_id)
        self._opening.pop(chip_id, None)
        return self.store.show_mat(chip_id)

    # ---- the loops

    def _report(self, chip_id, where, error, now=None):
        """Print a fault of one mat, at most once a minute per mat and place (the loops run several times a second)"""
        now = time.time() if now is None else now
        if now - self._reported.get((chip_id, where), -REPORT_EVERY_S) >= REPORT_EVERY_S:
            self._reported[(chip_id, where)] = now
            print(f"{where} {chip_id}: {type(error).__name__}: {error}")

    def pump(self):
        for chip_id, feed in list(self.feeds.items()):
            try:  # one failing mat must not stop the others
                item = feed.take()
                engine = self.engines.get(chip_id)   # None: removed while this round ran
                if item is not None and engine is not None:
                    engine.feed(*item)
            except Exception as error:
                self._report(chip_id, "pump", error)

    def tick(self, now):
        """Once a second: timeline, alerts (logged, a raised one is pushed to the registered phones), MQTT discovery"""
        if self._last_tick is not None and not 0 <= now - self._last_tick <= CLOCK_JUMP_S:
            self.alerts.reset_holds()  # the clock jumped (a Pi sets it from the network after boot) or the loop stalled
        self._last_tick = now
        try:
            self._discover(now)
        except Exception as error:
            self._report("mqtt", "discovery", error, now)
        states = []
        for chip_id, engine in list(self.engines.items()):
            try:
                snap = engine.snapshot()
                if snap["online"]:  # an offline mat leaves a gap in the timeline ("no data")
                    states.append((chip_id, snap["posture"], snap["risk"]))
                self._update_alerts(chip_id, snap["risk"], snap["online"], now)
            except Exception as error:
                self._report(chip_id, "tick", error, now)
        # an alert saved before a restart for a mat that has no engine (gone from the broker, USB mat no longer set up):
        # the mat counts as offline, so the alert follows the offline rules instead of staying open for ever
        for chip_id in {a["chip_id"] for a in self.alerts.open_alerts()} - set(self.engines):
            try:
                self._update_alerts(chip_id, "offline", False, now)
            except Exception as error:
                self._report(chip_id, "tick", error, now)
        self.store.record_states(now, states)

    def _update_alerts(self, chip_id, risk, online, now):
        for kind, alert in self.alerts.update(chip_id, risk, online, now):
            self.store.log(now, f"alert {kind}", chip_id, None, {"alert": alert["id"], "kind": alert["kind"]})
            if kind == "raised":
                self.pusher.notify(alert)

    def run_loops(self):
        def pump_loop():
            while not self._stop.wait(PUMP_S):
                try:
                    self.pump()
                except Exception as error:  # one bad frame must not stop the server
                    print(f"pump: {type(error).__name__}: {error}")

        def tick_loop():
            last_purge = 0.0
            while not self._stop.wait(TICK_S):
                now = time.time()
                try:
                    self.tick(now)
                    if now - last_purge >= PURGE_EVERY_S:
                        last_purge = now
                        self.store.purge(now, days=self.settings.get("retention_days"))
                except Exception as error:
                    print(f"tick: {type(error).__name__}: {error}")

        self._threads = [threading.Thread(target=loop, daemon=True) for loop in (pump_loop, tick_loop)]
        for thread in self._threads:
            thread.start()

    def stop(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
        for feed in self.feeds.values():
            if hasattr(feed, "stop"):
                feed.stop()
        if self.discovery is not None:
            self.discovery.stop()


def import_nicknames(store, path):
    """mats.json nicknames become a mat's name, once (names set on the server win)"""
    known = store.mats()
    for chip_id, name in general.load_mat_names(path).items():
        if not (known.get(chip_id) or {}).get("name"):
            store.set_meta(chip_id, {"name": name})


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m server", description="SmartMat server (headless)")
    parser.add_argument("--demo", nargs="?", type=int, const=5, default=0, metavar="N",
                        help="add N demo mats replaying samples/seat_take1.json (default 5)")
    parser.add_argument("--port", type=int, default=getattr(config, "SERVER_PORT", 8000))
    parser.add_argument("--data-dir", type=Path, default=paths.APP_DIR,
                        help="database, profiles/ and mats.json (default: the app data folder)")
    args = parser.parse_args(argv)

    args.data_dir.mkdir(parents=True, exist_ok=True)
    calibration.PROFILES_DIR = args.data_dir / "profiles"
    store = Store(args.data_dir / "smartmat.db")
    import_nicknames(store, args.data_dir / "mats.json")
    settings = Settings(store)
    alerts = AlertManager(high_hold_s=settings.get("alert_high_hold_s"), offline_hold_s=settings.get("alert_offline_s"),
                          on_change=store.save_alert, stamp=settings.stamp)
    alerts.restore(store.saved_alerts(), time.time())  # alerts open before a restart stay open and are not pushed again
    server = Server(store, alerts, demo=args.demo, serial_ports=getattr(config, "SERVER_SERIAL_PORTS", ()),
                    settings=settings)
    server.run_loops()
    http = make_server("0.0.0.0", args.port, create_app(store, server.alerts, server.engines, settings=settings, control=server),
                       threaded=True)
    stopping = threading.Event()

    def shut_down(*_):
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=http.shutdown, daemon=True).start()  # shutdown() blocks until serving ends

    signal.signal(signal.SIGINT, shut_down)
    signal.signal(signal.SIGTERM, shut_down)
    print(f"SmartMat server on http://0.0.0.0:{args.port} (data in {args.data_dir})")
    try:
        http.serve_forever()
    finally:
        server.stop()
        store.close()


if __name__ == "__main__":
    main()
