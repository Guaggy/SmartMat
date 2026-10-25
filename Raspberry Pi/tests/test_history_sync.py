"""Desktop history playback logic (client/history_sync.py) against the real Flask app over HTTP with the desktop's own
ServerClient: paging, decoding, the player, the numbers and the recording export. No Tk."""

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np
from werkzeug.serving import make_server

from client import history_sync
from client.server_client import ServerClient
from processing.recording import load_session
from server.alerts import AlertManager
from server.app import create_app
from server.engine import MatEngine
from server.store import Store

T0 = 1_700_000_000.0


def grid(value, rows=20, cols=20):
    out = np.zeros((rows, cols), dtype="uint8")
    out[5:8, 5:8] = value
    return out


def numbers(risk="low", **extra):
    return dict({"peak_kpa": 40.0, "risk": risk, "score": 0.5, "posture": "left", "occupied": True,
                 "hotspots": [{"id": 1, "peak_kpa": 40.0, "cells": 9, "centre": [6, 6], "active_s": 5, "persistent": True}],
                 "contact_cells": 9, "contact_area_cm2": 80.0, "load_kg": 12.34, "time_in_position_s": 3700,
                 "since_movement_s": 125, "since_reposition_s": None, "movements": 1, "repositions": 0}, **extra)


class LiveServerTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)
        app = create_app(self.store, AlertManager(), {"m1": MatEngine("m1", 20, 20)}, clock=lambda: T0 + 100000)
        http = make_server("127.0.0.1", 0, app)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.shutdown)
        self.client = ServerClient(f"http://127.0.0.1:{http.server_port}", timeout=5)
        # 7 periodic snapshots 5 min apart, an alert raise at +12 min and its clear at +26 min
        for i in range(7):
            self.store.add_snapshot(T0 + i * 300, "m1", "periodic", numbers("high" if i == 3 else "low"),
                                    grid(50 + i * 20), grid(80 + i * 20), unit="kPa", scale_max=50.0)
        alert = {"id": "a1", "kind": "high_risk"}
        self.store.add_snapshot(T0 + 720, "m1", "alert_raised", numbers("high"), grid(200), None, alert, "kPa", 50.0)
        self.store.add_snapshot(T0 + 1560, "m1", "alert_cleared", numbers("low"), None, None, alert, None, None)

    def load(self, **kwargs):
        ok, history = history_sync.fetch_range(self.client, "m1", T0 - 10, T0 + 5000, **kwargs)
        self.assertTrue(ok, history)
        return history

    def test_overview_lists_the_mats(self):
        ok, mats = self.client.get_overview()
        self.assertTrue(ok)
        self.assertEqual([m["id"] for m in mats], ["m1"])

    def test_the_whole_range_comes_back_in_order_with_grids(self):
        history = self.load()
        self.assertEqual(len(history), 9)
        self.assertEqual(history.times(), sorted(history.times()))
        self.assertFalse(history.truncated)
        self.assertEqual(history.grid(0).shape, (20, 20))

    def test_paging_gives_the_same_snapshots_as_one_request(self):
        whole = self.load()
        original = history_sync.PAGE
        history_sync.PAGE = 2
        self.addCleanup(setattr, history_sync, "PAGE", original)
        calls = []
        paged = self.load(progress=calls.append)
        self.assertEqual(paged.times(), whole.times())
        self.assertEqual(len(set(s["id"] for s in paged.snapshots)), 9)    # nothing twice at a page edge
        self.assertEqual(calls[-1], 9)
        self.assertGreater(len(calls), 3)

    def test_the_cap_stops_the_paging_and_says_so(self):
        history_sync.PAGE = 2
        self.addCleanup(setattr, history_sync, "PAGE", 300)
        history = self.load(max_snapshots=4)
        self.assertTrue(history.truncated)
        self.assertEqual(len(history), 4)

    def test_cancel_and_errors(self):
        ok, text = history_sync.fetch_range(self.client, "m1", T0, T0 + 10, cancelled=lambda: True)
        self.assertEqual((ok, text), (False, "cancelled"))
        ok, text = history_sync.fetch_range(self.client, "nope", T0, T0 + 10)
        self.assertFalse(ok)
        self.assertIn("404", text)
        ok, text = history_sync.fetch_range(ServerClient("http://127.0.0.1:9", timeout=1), "m1", T0, T0 + 10)
        self.assertFalse(ok)

    def test_grids_are_scaled_back_to_kpa_and_peak_differs_from_instant(self):
        history = self.load()
        self.assertAlmostEqual(history.grid(0, "instant").max(), 50 / 255 * 50.0, places=3)
        self.assertAlmostEqual(history.grid(0, "peak").max(), 80 / 255 * 50.0, places=3)
        raised = [i for i, _, _ in history.alert_markers()][0]
        self.assertFalse(history.has_peak(raised))
        self.assertAlmostEqual(history.grid(raised, "peak").max(), 200 / 255 * 50.0, places=3)   # falls back to instant
        offline = history.alert_markers()[-1][0]
        self.assertIsNone(history.grid(offline))                                                 # the clear had no picture
        self.assertEqual(history.top("instant"), max(history.grid(i).max() for i in range(len(history)) if history.grid(i) is not None))
        self.assertGreater(history.top("peak"), history.top("instant") - 1e-9)

    def test_alert_markers_and_risk_strip(self):
        history = self.load()
        self.assertEqual([(kind, alert) for _, kind, alert in history.alert_markers()],
                         [("raised", "high_risk"), ("cleared", "high_risk")])
        self.assertEqual(len(history.risk_strip()), 9)
        self.assertIn("high", history.risk_strip())

    def test_numbers_are_indicative_text(self):
        text = dict(history_sync.numbers(self.load().snapshots[0]))
        self.assertEqual(text["Peak pressure"], "40.0 kPa")
        self.assertEqual(text["Load (indicative)"], "12.3 kg")
        self.assertEqual(text["Contact area"], "80 cm²")
        self.assertEqual(text["Time since movement"], "2 min")
        self.assertEqual(text["Time in position"], "1 h 01 min")
        self.assertEqual(text["Hotspots"], "1: 40 kPa (persistent)")
        self.assertEqual(text["Posture"], "left")
        self.assertIn("0.50", text["Risk"])

    def test_numbers_cope_with_missing_values(self):
        text = dict(history_sync.numbers({"t": T0, "reason": "alert_cleared", "alert_kind": "offline", "risk": "offline",
                                          "posture": "none", "hotspots": []}))
        self.assertEqual((text["Peak pressure"], text["Load (indicative)"], text["Posture"], text["Hotspots"]),
                         ("-", "-", "unoccupied", "none"))
        self.assertIn("alert cleared: offline", text["Time"])

    def test_player_steps_stops_at_the_end_and_replays(self):
        player = history_sync.Player(self.load())
        self.assertFalse(player.tick())                # paused: nothing moves
        self.assertTrue(player.play())
        steps = 0
        while player.tick():
            steps += 1
        self.assertEqual((steps, player.index, player.playing), (8, 8, False))
        self.assertTrue(player.play())                 # at the end, play starts again from the first
        self.assertEqual(player.index, 0)
        self.assertEqual(player.seek(99), 8)
        self.assertEqual(player.seek(-3), 0)
        self.assertEqual(player.delay_ms(), 500)
        player.speed = 10
        self.assertEqual(player.delay_ms(), 100)

    def test_player_jumps_between_alerts(self):
        history = self.load()
        player = history_sync.Player(history)
        first, last = (i for i, _, _ in history.alert_markers())
        self.assertEqual(player.next_alert(1), first)
        player.seek(first)
        self.assertEqual(player.next_alert(1), last)
        self.assertIsNone(player.next_alert(-1))
        player.seek(last)
        self.assertIsNone(player.next_alert(1))
        self.assertEqual(player.next_alert(-1), first)

    def test_an_empty_history_plays_nothing(self):
        ok, history = history_sync.fetch_range(self.client, "m1", T0 + 10_000, T0 + 11_000)
        self.assertTrue(ok)
        player = history_sync.Player(history)
        self.assertEqual((len(history), player.play(), player.grid(), player.current()), (0, False, None, None))

    def test_saved_recording_loads_with_the_desktop_loader(self):
        history = self.load()
        path = self.dir / "m1_history.json"
        count = history_sync.save_recording(history, path, "instant")
        self.assertEqual(count, 8)                     # the offline clear had no picture
        frames, times, metadata, events = load_session(path, with_timestamps=True, with_details=True)
        self.assertEqual((len(frames), frames[0].shape), (8, (20, 20)))
        self.assertIsNotNone(times)                    # strictly increasing, so playback keeps the real spacing
        self.assertEqual(metadata["mat_id"], "m1")
        self.assertEqual(metadata["value_max"], 50.0)
        self.assertAlmostEqual(frames[0].max() * metadata["value_max"] / 1000, history.grid(0).max(), places=1)
        self.assertEqual([e["kind"] for e in events], ["alert_raised"])
        self.assertEqual(events[0]["frame_index"], 3)  # indexes into the saved frames, not the snapshots
        peak = history_sync.to_recording(history, "peak")
        self.assertGreater(np.max(peak["frames"][0]["raw"]), np.max(json.loads(path.read_text())["frames"][0]["raw"]))

    def test_equal_timestamps_are_nudged_apart_and_an_all_blind_range_is_refused(self):
        snap = {"t": T0, "unit": "kPa", "scale_max": 50.0, "grid": grid(100).tolist()}
        recording = history_sync.to_recording(history_sync.History("m1", [dict(snap), dict(snap, id=2)]))
        times = [f["timestamp"] for f in recording["frames"]]
        self.assertLess(times[0], times[1])
        with self.assertRaises(ValueError):
            history_sync.to_recording(history_sync.History("m1", [{"t": T0, "grid": None}]))


if __name__ == "__main__":
    unittest.main()
