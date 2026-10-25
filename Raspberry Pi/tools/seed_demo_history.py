"""Fill the server database with DEMO history: the scripted demo scenario simulated on a fast clock and run through the
real server code (engine, alerts, timeline, history recorder), so the playback scrubber and exports have a day of data.

    python tools/seed_demo_history.py --days 1 --mats 3 [--data-dir DIR]

Stop the server first. Everything is written for chip ids `demo-1`.. (they carry the DEMO badge) and logged as
"demo history seeded"; other mats are not touched. Running it twice for the same days adds a second set of rows."""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # the app folder, so its modules import from anywhere

import paths
from server.__main__ import DEMO_PREFIX, Server, demo_profile
from server.alerts import AlertManager
from server.demo_scenario import PERIOD_S, scenario_grid
from server.engine import MatEngine
from server.history import HistoryRecorder
from server.store import Store

STEP_S = 1.5   # demo seconds between frames: under TEMPORAL_MAX_GAP_S, so the analysis does not see a data gap


class NoPush:
    def notify(self, alert):
        pass


def seed(store, mats=3, days=1.0, end=None, step_s=STEP_S, interval_s=None, progress=None):
    """Simulate `days` of the scenario for `mats` demo mats ending at `end` (default now). Returns snapshots written."""
    end = time.time() if end is None else end
    start = end - days * 86400
    alerts = AlertManager(on_change=store.save_alert)
    recorder = HistoryRecorder(store, enabled=True, **({} if interval_s is None else {"interval_s": interval_s}))
    server = Server(store, alerts, demo=0, use_mqtt=False, pusher=NoPush(), history=recorder)
    now = [start]
    offsets = {}
    for index in range(mats):
        chip_id = f"{DEMO_PREFIX}{index + 1}"
        engine = MatEngine(chip_id, 20, 20, profile=demo_profile(20, 20))
        engine.clock = lambda: now[0]
        server.scenario_mats.add(chip_id)   # relief_minutes and the alert delay of the demo scenario
        server._add(chip_id, engine, feed=None)
        offsets[chip_id] = PERIOD_S * index / mats
    steps = int((end - start) / step_s)
    for n in range(steps):
        now[0] = t = start + n * step_s
        for chip_id, engine in server.engines.items():
            engine.feed(scenario_grid(offsets[chip_id] + (t - start)), t)
        server.tick(t)
        if progress and n % 5000 == 0:
            progress(n, steps)
    store.log(end, "demo history seeded", None, "seed_demo_history", {"mats": mats, "days": days})
    return sum(len(store.snapshots(f"{DEMO_PREFIX}{i + 1}", start, end, 1000000)[0]) for i in range(mats))


def main():
    parser = argparse.ArgumentParser(description="Seed demo history (clearly demo data: chip ids demo-N)")
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument("--mats", type=int, default=3)
    parser.add_argument("--data-dir", type=Path, default=paths.APP_DIR)
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(args.data_dir / "smartmat.db")
    started = time.time()
    count = seed(store, args.mats, args.days, progress=lambda n, total: print(f"{100 * n // total}%", end=" ", flush=True))
    store.close()
    print(f"\n{count} snapshots for {args.mats} demo mats in {time.time() - started:.0f} s ({args.data_dir})")


if __name__ == "__main__":
    main()
