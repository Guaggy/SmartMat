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
from server.store import Store

PUMP_S = 0.25   # ponytail: each mat is analysed at most 4 frames/s; the per-cell calibration loop costs ~13 ms a frame
TICK_S = 1.0
PURGE_EVERY_S = 3600
OPEN_RETRY_S = 10
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
    def __init__(self, store, alerts, demo=0, serial_ports=(), use_mqtt=True):
        self.store, self.alerts = store, alerts
        self.engines = {}   # chip_id -> MatEngine (read by the web app)
        self.feeds = {}     # chip_id -> DemoMat / MqttMat / SerialBridge
        self._opening = {}  # chip_id -> time an MQTT mat was last tried
        self._stop = threading.Event()
        self._threads = []
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

    def _add(self, chip_id, engine, feed):
        self.engines[chip_id], self.feeds[chip_id] = engine, feed

    # ---- MQTT mats come and go

    def _discover(self, now):
        if self.discovery is None:
            return
        for chip_id, shape in list(self.discovery.mats.items()):
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
        if self._stop.is_set():
            source.stop()
            return
        self._add(chip_id, self._mqtt_engine(chip_id), MqttMat(source))
        self.store.log(time.time(), "mat connected", chip_id)

    # ---- the loops

    def pump(self):
        for chip_id, feed in list(self.feeds.items()):
            item = feed.take()
            if item is not None:
                self.engines[chip_id].feed(*item)

    def tick(self, now):
        """Once a second: timeline, alerts (logged), MQTT discovery"""
        self._discover(now)
        states = []
        for chip_id, engine in list(self.engines.items()):
            snap = engine.snapshot()
            states.append((chip_id, snap["posture"], snap["risk"]))
            for kind, alert in self.alerts.update(chip_id, snap["risk"], snap["online"], now):
                self.store.log(now, f"alert {kind}", chip_id, None, {"alert": alert["id"], "kind": alert["kind"]})
        self.store.record_states(now, states)

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
                        self.store.purge(now)
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
    server = Server(store, AlertManager(), demo=args.demo, serial_ports=getattr(config, "SERVER_SERIAL_PORTS", ()))
    server.run_loops()
    http = make_server("0.0.0.0", args.port, create_app(store, server.alerts, server.engines), threaded=True)
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
