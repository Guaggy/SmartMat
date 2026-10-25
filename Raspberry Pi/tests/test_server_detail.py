"""MatEngine.detail and /api/mats/<id>?layer=&view=: the extra grids and readouts the dashboard asks for"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from processing import calibration
from server.alerts import AlertManager
from server.app import create_app
from server.engine import LAYERS, MatEngine
from server.store import Store


def blob(row, col, kpa=30.0):
    grid = np.zeros((20, 20))
    grid[row - 2:row + 3, col - 2:col + 3] = kpa / 50 * 1000   # default curve: 1000 = 50 kPa
    return grid


def fed(grid, steps=60, size_mm=(400, 400)):
    engine = MatEngine("m1", 20, 20, size_mm=size_mm)
    for step in range(steps):
        engine.feed(grid, step * 0.1)
    return engine


class DetailTests(unittest.TestCase):
    def test_nothing_before_the_first_frame(self):
        self.assertEqual(MatEngine("m1", 20, 20).detail("exposure"), {})

    def test_readouts_for_a_load_on_the_sitters_left_front(self):
        detail = fed(blob(15, 15)).detail()
        self.assertEqual((detail["layer"], detail["view"], "grid" in detail), ("pressure", "live", False))
        self.assertEqual(detail["contact_cells"], 25)
        self.assertAlmostEqual(detail["contact_area_cm2"], 25 * 4.0, places=1)   # 20 mm cells = 4 cm2
        # 25 cells x 30 kPa x 4 cm2 = 300 N: about 30.6 kg, indicative only
        self.assertAlmostEqual(detail["load_kg"], 300 / 9.81, delta=0.2)
        self.assertGreater(detail["left_percent"], 90)     # column 0 is the sitter's right, so high columns are left
        self.assertGreater(detail["front_percent"], 90)    # the last row is the front edge
        self.assertEqual([round(v) for v in detail["cop"]], [15, 15])
        self.assertEqual(detail["cell_area_cm2"], 4.0)
        json.dumps(detail)

    def test_balance_is_even_for_a_centred_load(self):
        grid = np.zeros((20, 20))
        grid[8:12, 8:12] = 600   # rows and columns 8-11: the middle of a 20 x 20 mat
        detail = fed(grid).detail()
        self.assertAlmostEqual(detail["left_percent"], 50, delta=1)
        self.assertAlmostEqual(detail["front_percent"], 50, delta=1)

    def test_other_layers_come_from_the_signals_and_unknown_names_fall_back(self):
        engine = fed(blob(10, 10))
        for layer in LAYERS[1:]:
            detail = engine.detail(layer)
            self.assertEqual((detail["layer"], len(detail["grid"]), len(detail["grid"][0])), (layer, 20, 20))
            self.assertGreater(detail["scale_max"], 0)
        exposure = np.array(engine.detail("exposure")["grid"], dtype=float)
        self.assertGreater(exposure[10, 10], 0)
        self.assertEqual(exposure[0, 0], 0)
        self.assertEqual(engine.detail("nonsense")["layer"], "pressure")
        self.assertNotIn("grid", engine.detail("nonsense"))

    def test_average_view_smooths_the_last_frames(self):
        engine = fed(blob(10, 10), steps=30)
        for step in range(4):
            engine.feed(np.zeros((20, 20)), 3 + step * 0.1)   # four empty frames after a loaded one
        live = np.array(engine.snapshot()["grid"], dtype=float)
        average = np.array(engine.detail("pressure", "average")["grid"], dtype=float)
        self.assertEqual(engine.detail("pressure", "average")["view"], "average")
        self.assertEqual(live[10, 10], 0)             # the live frame is empty
        self.assertGreater(average[10, 10], 0)        # the average still remembers the load

    def test_idle_calls_leave_the_snapshot_alone(self):
        engine = fed(blob(10, 10))
        before = json.dumps(engine.snapshot(6.0))
        engine.detail("exposure", "average")
        self.assertEqual(json.dumps(engine.snapshot(6.0)), before)


class MotionAgeTests(unittest.TestCase):
    def test_none_until_a_movement_then_seconds_since_it(self):
        engine = MatEngine("m1", 20, 20)
        self.assertEqual(engine.motion_ages(), {"since_movement_s": None, "since_reposition_s": None})
        engine = fed(blob(10, 10), steps=20)
        engine.feed(blob(10, 10) * 0, 2.5)
        engine.motion.last_movement_event = 1.0
        ages = engine.motion_ages()
        self.assertEqual(ages["since_movement_s"], 1.5)
        self.assertIsNone(ages["since_reposition_s"])
        self.assertEqual({k: engine.snapshot()[k] for k in ages}, ages)


class DetailApiTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        patcher = mock.patch.object(calibration, "PROFILES_DIR", self.dir / "profiles")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = Store(self.dir / "smartmat.db", lockout_attempts=0, lockout_s=60)
        self.addCleanup(self.store.close)
        self.engines = {"m1": fed(blob(10, 10)), "m2": MatEngine("m2", 20, 20)}
        for engine in self.engines.values():
            engine.clock = lambda: 6.0
        self.client = create_app(self.store, AlertManager(0, 0), self.engines, clock=lambda: 6.0).test_client()

    def test_layer_and_view_arrive_in_the_snapshot(self):
        plain = self.client.get("/api/mats/m1").get_json()["snapshot"]
        self.assertEqual((plain["unit"], plain["layer"], plain["view"]), ("kPa", "pressure", "live"))
        self.assertIn("load_kg", plain)
        layer = self.client.get("/api/mats/m1?layer=exposure").get_json()["snapshot"]
        self.assertEqual((layer["layer"], layer["unit"]), ("exposure", "kPa*min"))
        self.assertEqual(layer["hotspots"], plain["hotspots"])
        self.assertEqual(self.client.get("/api/mats/m1?view=average").get_json()["snapshot"]["view"], "average")
        self.assertEqual(self.client.get("/api/mats/m1?layer=%00&view=x").get_json()["snapshot"]["layer"], "pressure")

    def test_rows_carry_the_motion_ages_for_the_phone_app(self):
        self.engines["m1"].motion.last_movement_event = 4.0
        row = self.client.get("/api/mats/m1").get_json()
        self.assertEqual((row["since_movement_s"], row["since_reposition_s"]), (round(self.engines["m1"].last_t - 4.0, 1), None))
        rows = {r["id"]: r for r in self.client.get("/api/overview").get_json()["mats"]}
        self.assertEqual(rows["m1"]["since_movement_s"], row["since_movement_s"])
        self.assertIsNone(rows["m2"]["since_movement_s"])

    def test_the_overview_does_not_carry_the_extras(self):
        rows = self.client.get("/api/overview").get_json()["mats"]
        self.assertNotIn("snapshot", rows[0])
        self.assertNotIn("load_kg", rows[0])

    def test_a_mat_without_frames_has_no_snapshot(self):
        self.assertIsNone(self.client.get("/api/mats/m2").get_json()["snapshot"])


if __name__ == "__main__":
    unittest.main()
