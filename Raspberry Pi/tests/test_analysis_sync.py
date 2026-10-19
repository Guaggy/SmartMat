"""Desktop <-> server analysis settings: key mapping, compare, push, pull and the preview, against the real Flask app over
HTTP with the desktop's own ServerClient. No Tk."""

import copy
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from werkzeug.serving import make_server

import analysis_sync
import config
from paths import resource_path
from processing.indices import default_indices
from processing.recording import load_session
from processing.settings import default_settings, flatten_preset, unflatten_preset, validate_settings
from server.alerts import AlertManager
from server.app import create_app
from server.engine import MatEngine
from server.settings import Settings, keys, spec_of
from server.store import Store
from server_client import ServerClient

ADMIN, NURSE = "1234", "5678"
SAMPLE = resource_path("samples/seat_take1.json")
EAGER = [  # a risk index that is over its limit as soon as anyone sits down
    {"name": "Load", "layer": "map", "threshold": 1.0, "near_fraction": 0.5,
     "terms": [{"signal": "exposure", "window_min": 15, "reference": 0.0001, "weight": 1.0, "inverted": False}]},
    {"name": "Overview", "layer": "summary", "threshold": 1.0, "near_fraction": 0.5,
     "terms": [{"source": "Load", "reducer": "peak", "region": "mat", "reference": 1.0, "weight": 1.0, "inverted": False}]},
]


def desktop_settings():
    """What DesktopApp.current_settings() returns on a fresh start: the default preset plus the default indices"""
    settings = default_settings()
    settings["indices"] = default_indices()
    return settings


class LiveServerTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)
        self.store.add_user("Admin", "admin", ADMIN)
        self.store.add_user("Kari", "user", NURSE)
        self.settings = Settings(self.store)
        self.alerts = AlertManager(stamp=self.settings.stamp)
        self.engines = {"m1": MatEngine("m1", 20, 20), "m2": MatEngine("m2", 20, 20)}
        app = create_app(self.store, self.alerts, self.engines, settings=self.settings)
        self.http = make_server("127.0.0.1", 0, app)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.shutdown)
        self.client = ServerClient(f"http://127.0.0.1:{self.http.server_port}", timeout=5)

    def page(self, chip="m1"):
        ok, page = self.client.get_config(chip)
        self.assertTrue(ok, page)
        return page

    # ---- the key space

    def test_the_desktop_preset_flattens_to_exactly_the_servers_engineering_keys(self):
        flat = flatten_preset(default_settings())
        server_keys = [key for key in keys() if analysis_sync.is_sync_key(key) and key != "indices"]
        self.assertEqual(sorted(flat), sorted(server_keys))
        self.assertEqual(unflatten_preset(flat), default_settings())
        for key in flat:
            self.assertIsNotNone(spec_of(key))

    # ---- compare

    def test_a_fresh_desktop_matches_a_fresh_server(self):
        rows = analysis_sync.compare(desktop_settings(), self.page())
        self.assertEqual([row["key"] for row in rows if row["differs"]], [])
        self.assertEqual(len(rows), len(flatten_preset(default_settings())) + 1)        # every preset key and the indices
        self.assertTrue(all(row["source"] == "factory" for row in rows))

    def test_a_changed_value_is_listed_first_with_where_the_server_value_comes_from(self):
        self.client.put_config("m1", {"hotspots.activate_kpa": 28.0}, ADMIN, "test")
        self.client.put_config(None, {"movement.small_score": 0.2}, ADMIN, "site")
        settings = desktop_settings()
        settings["hotspots"]["activate_kpa"] = 33.0
        rows = analysis_sync.compare(settings, self.page())
        self.assertEqual(rows[0]["key"], "hotspots.activate_kpa")
        self.assertEqual((rows[0]["local"], rows[0]["server"], rows[0]["source"], rows[0]["differs"]), (33.0, 28.0, "mat", True))
        site = next(row for row in rows if row["key"] == "movement.small_score")
        self.assertEqual((site["server"], site["source"], site["differs"]), (0.2, "site", True))   # the desktop still has 0.15
        self.assertEqual(sum(row["differs"] for row in rows), 2)

    def test_the_risk_knobs_change_the_server_side_indices(self):
        self.client.put_config("m1", {"near_percent": 60}, ADMIN)
        row = next(r for r in analysis_sync.compare(desktop_settings(), self.page()) if r["key"] == "indices")
        self.assertTrue(row["differs"])                                    # the built-in indices are tuned: near 60 % now
        self.assertEqual({d["near_fraction"] for d in row["server"]}, {0.6})

    def test_settings_without_indices_leave_that_row_out_of_the_comparison(self):
        settings = default_settings()      # an older preset: no indices
        row = next(r for r in analysis_sync.compare(settings, self.page()) if r["key"] == "indices")
        self.assertFalse(row["differs"])

    def test_small_float_noise_is_not_a_difference(self):
        settings = desktop_settings()
        settings["hotspots"]["activate_kpa"] = 20.0 + 1e-12
        self.assertEqual([r for r in analysis_sync.compare(settings, self.page()) if r["differs"]], [])

    # ---- push

    def test_pushing_the_differences_sets_the_mats_own_layer_and_makes_the_two_match(self):
        settings = desktop_settings()
        settings["hotspots"]["activate_kpa"] = 33.0
        settings["contact_threshold_kpa"] = 2.5
        settings["indices"] = copy.deepcopy(EAGER)
        changes = analysis_sync.changes_to_push(analysis_sync.compare(settings, self.page()))
        self.assertEqual(sorted(changes), ["contact_threshold_kpa", "hotspots.activate_kpa", "indices"])
        ok, answer = self.client.put_config("m1", changes, ADMIN, "from the desktop")
        self.assertTrue(ok, answer)
        self.assertEqual((answer["user"], answer["stamp"]), ("Admin", "s0.m1"))
        self.assertEqual([r for r in analysis_sync.compare(settings, self.page()) if r["differs"]], [])
        self.assertEqual(self.page("m2")["stamp"], "s0.m0")                  # another mat is untouched
        self.assertEqual(self.settings.get("contact_threshold_kpa", "m2"), config.CONTACT_THRESHOLD_KPA)   # this PC's config.py may differ from the example
        ok, history = self.client.get_history("m1")
        self.assertEqual((history[0]["user"], history[0]["reason"]), ("Admin", "from the desktop"))
        self.assertEqual(sorted(history[0]["changes"]), ["contact_threshold_kpa", "hotspots.activate_kpa", "indices"])

    def test_the_site_layer_can_be_pushed_to_as_well(self):
        ok, answer = self.client.put_config(None, {"hotspots.min_cells": 3}, ADMIN, "site")
        self.assertTrue(ok, answer)
        self.assertEqual(self.settings.get("hotspots.min_cells", "m2"), 3)

    def test_a_push_the_server_refuses_says_why_and_changes_nothing(self):
        ok, text = self.client.put_config("m1", {"hotspots.deactivate_kpa": 99.0}, ADMIN)
        self.assertFalse(ok)
        self.assertIn("Hotspot", text)
        self.assertEqual(self.page()["version"], 0)
        self.assertEqual(self.client.put_config("m1", {"near_percent": 70}, "0000")[1], "403 Wrong PIN")
        self.assertIn("admin", self.client.put_config("m1", {"near_percent": 70}, NURSE)[1].lower())
        ok, text = self.client.get_config("nope")
        self.assertFalse(ok)
        self.assertTrue(text.startswith("404"), text)

    def test_nothing_to_push_when_the_two_match(self):
        self.assertEqual(analysis_sync.changes_to_push(analysis_sync.compare(desktop_settings(), self.page())), {})

    def test_only_the_chosen_rows_are_pushed(self):
        settings = desktop_settings()
        settings["hotspots"]["activate_kpa"] = 33.0
        settings["movement"]["small_score"] = 0.2
        rows = analysis_sync.compare(settings, self.page())
        self.assertEqual(analysis_sync.changes_to_push(rows, only={"movement.small_score"}), {"movement.small_score": 0.2})

    # ---- pull

    def test_pulling_gives_settings_the_desktop_accepts_and_that_match_afterwards(self):
        self.client.put_config("m1", {"hotspots.activate_kpa": 28.0, "indices": EAGER, "near_percent": 50}, ADMIN)
        page = self.page()
        pulled = analysis_sync.settings_from_server(page)
        self.assertEqual(pulled["hotspots"]["activate_kpa"], 28.0)
        self.assertEqual([d["name"] for d in pulled["indices"]], ["Load", "Overview"])
        self.assertEqual(validate_settings(pulled)["hotspots"]["activate_kpa"], 28.0)
        self.assertEqual([r for r in analysis_sync.compare(pulled, page) if r["differs"]], [])

    def test_a_built_in_server_index_is_pulled_as_real_definitions(self):
        self.client.put_config("m1", {"relief_minutes": 60}, ADMIN)
        pulled = analysis_sync.settings_from_server(self.page())
        reference = [t["reference"] for d in pulled["indices"] for t in d["terms"] if t.get("signal") == "since_relief"]
        self.assertEqual(reference, [3600.0])

    def test_values_the_desktop_would_refuse_are_reported(self):
        page = self.page()
        for item in page["settings"]:
            if item["key"] == "hotspots.deactivate_kpa":
                item["value"] = 99.0
        with self.assertRaises(ValueError):
            analysis_sync.settings_from_server(page)


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.frames, self.times = load_session(SAMPLE, with_timestamps=True)
        self.resolved = analysis_sync.server_values(self.server_page())

    @staticmethod
    def server_page():
        return {"settings": Settings().describe("m1")}

    def replay(self, **changes):
        return analysis_sync.Replay(self.frames, self.times, dict(self.resolved, **changes))

    def test_the_whole_take_is_replayed_and_every_second_is_counted(self):
        result, = analysis_sync.run([self.replay()])
        self.assertGreater(result["frames"], 100)
        self.assertAlmostEqual(result["duration_s"], self.times[-1] - self.times[0], delta=0.5)
        self.assertAlmostEqual(sum(result["risk_seconds"].values()), result["duration_s"], delta=1.5)
        self.assertEqual(result["alerts"], [])                                      # 40 s of sitting is nowhere near an alert
        self.assertGreater(result["risk_seconds"]["low"], 20)

    def test_it_never_feeds_more_than_the_servers_rate(self):
        result, = analysis_sync.run([self.replay()])
        self.assertLessEqual(result["frames"], 4 * result["duration_s"] + 2)

    def test_only_the_first_part_can_be_replayed(self):
        replay = analysis_sync.Replay(self.frames, self.times, self.resolved, max_s=10)
        result, = analysis_sync.run([replay])
        self.assertLessEqual(result["duration_s"], 10.5)
        self.assertGreater(result["frames"], 20)

    def test_other_settings_give_another_answer_and_the_alert_shows_when_it_would_come(self):
        eager = dict(indices=EAGER, alert_high_hold_s=5)
        before, after = analysis_sync.run([self.replay(), self.replay(**eager)])
        self.assertEqual(before["alerts"], [])
        self.assertGreaterEqual(len(after["alerts"]), 1)
        first = after["alerts"][0]
        self.assertEqual(first["kind"], "high_risk")
        self.assertTrue(8 < first["t_raised"] < 35, first)
        self.assertEqual(after["first_alert_s"], first["t_raised"])
        self.assertGreater(after["risk_seconds"]["high"], 5)
        self.assertEqual(before["risk_seconds"]["high"], 0)

    def test_a_longer_alert_delay_holds_the_alert_back(self):
        eager_fast = self.replay(indices=EAGER, alert_high_hold_s=5)
        eager_slow = self.replay(indices=EAGER, alert_high_hold_s=20)
        fast, slow = analysis_sync.run([eager_fast, eager_slow])
        self.assertGreaterEqual(len(fast["alerts"]), 1)
        self.assertTrue(not slow["alerts"] or slow["alerts"][0]["t_raised"] > fast["alerts"][0]["t_raised"] + 10, (fast, slow))

    def test_the_replay_can_be_stepped_and_cancelled(self):
        replay = self.replay()
        progress = []
        self.assertLess(replay.step(8), 1.0)
        self.assertFalse(replay.done())
        seen = []
        self.assertIsNone(analysis_sync.run([replay], progress=progress.append, cancelled=lambda: bool(seen.append(1)) or len(seen) > 2))
        self.assertLessEqual(len(progress), 2)

    def test_progress_runs_from_zero_to_one_over_all_replays(self):
        progress = []
        analysis_sync.run([self.replay(), self.replay()], progress=progress.append)
        self.assertEqual(progress, sorted(progress))
        self.assertAlmostEqual(progress[-1], 1.0)
        self.assertTrue(any(p < 0.5 for p in progress) and any(p > 0.5 for p in progress))

    def test_a_recording_without_usable_times_is_replayed_at_ten_frames_a_second(self):
        replay = analysis_sync.Replay(self.frames[:60], None, self.resolved)
        result, = analysis_sync.run([replay])
        self.assertAlmostEqual(result["duration_s"], 5.9, delta=0.4)

    def test_the_summary_compares_the_two_runs_in_plain_words(self):
        before, after = analysis_sync.run([self.replay(), self.replay(indices=EAGER, alert_high_hold_s=5)])
        text = "\n".join(analysis_sync.summary_lines(before, after))
        self.assertIn("Alerts the server would raise: 0 now,", text)
        self.assertIn("Time at high risk: 0 s now,", text)

    def test_seconds_are_written_for_people(self):
        self.assertEqual([analysis_sync.format_seconds(v) for v in (None, 5, 75, 3725)], ["-", "5 s", "1 min 15 s", "1 h 02 min"])


if __name__ == "__main__":
    unittest.main()
