"""Server runner: demo mats replay the seat recording into engines and show up in /api/overview."""

import shutil
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from server.__main__ import DemoMat, Server, import_nicknames, load_frames
from server.alerts import AlertManager
from server.app import create_app
from server.store import Store


class DemoMatTests(unittest.TestCase):
    def test_offset_speed_loop_and_mirror(self):
        frames = [(np.full((2, 2), float(i)), 100.0 + i) for i in range(10)]
        frames[0][0][0, 0] = -1
        now = [50.0]
        mat = DemoMat(frames, offset_s=2, speed=3, wall=lambda: now[0])
        self.assertEqual(mat.take()[0][0, 1], 2)          # starts `offset_s` into the recording
        now[0] += 1                                      # 1 s wall = 3 s demo time
        grid, t = mat.take()
        self.assertEqual((grid[0, 1], t), (5, 53))
        now[0] += 10                                     # past the end: loops the seated part (no empty mat here)
        self.assertEqual(mat.take()[0][0, 1], (2 + 33 - 9) % 9)
        mirrored = DemoMat(frames, mirror=True, wall=lambda: now[0])
        self.assertEqual(mirrored.take()[0][0, 1], -1)
        moved = DemoMat(frames, shift=(0, 1), wall=lambda: now[0]).take()[0]
        self.assertEqual((moved[0, 0], moved[0, 1]), (0, -1))     # load moved one cell right, empty behind it


class SmokeTests(unittest.TestCase):
    def test_demo_mats_are_listed_with_the_demo_flag_and_a_risk(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        store = Store(folder / "smartmat.db")
        self.addCleanup(store.close)
        (folder / "mats.json").write_text('{"demo-2": "Chair by the window"}', encoding="utf-8")
        import_nicknames(store, folder / "mats.json")
        server = Server(store, AlertManager(), demo=3, use_mqtt=False)
        self.addCleanup(server.stop)
        for _ in range(4):
            server.pump()
            time.sleep(0.05)
        server.tick(time.time())
        client = create_app(store, server.alerts, server.engines).test_client()
        rows = client.get("/api/overview").get_json()["mats"]
        self.assertEqual(sorted(row["id"] for row in rows), ["demo-1", "demo-2", "demo-3"])
        for row in rows:
            self.assertTrue(row["demo"])
            self.assertTrue(row["online"])
            self.assertIn(row["risk"], ("high", "medium", "low", "none"))
        self.assertEqual(next(r for r in rows if r["id"] == "demo-2")["name"], "Chair by the window")
        self.assertEqual(len(store.timeline("demo-1", 0)), 1)
        self.assertEqual(client.get("/api/mats/demo-1").get_json()["snapshot"]["unit"], "kPa")

    def test_sample_loads_at_its_grid_size(self):
        frames = load_frames()
        self.assertEqual(frames[0][0].shape, (20, 20))
        self.assertGreater(len(frames), 100)


if __name__ == "__main__":
    unittest.main()
