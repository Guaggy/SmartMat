"""Web dashboard: per-mat store, snapshot, addresses, and the desktop feeding it."""

import socket
import tkinter as tk
import unittest
from unittest import mock

import numpy as np

from gui import web
from processing.indices import IndexMonitor

SHAPE = (16, 15)
MATS = [{"id": "aaa111", "name": "Bed", "rows": 16, "cols": 15},
        {"id": "bbb222", "name": "bbb222", "rows": 20, "cols": 12}]


def snapshot(value=5.0):
    return {"unit": "kPa", "scale_max": 50.0, "grid": [[value]], "occupied": True,
            "hotspots": [], "indices": []}


class StoreAndAddressTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()
        web.update([])
        self.addCleanup(web.update, [])

    def test_page_is_served_without_any_mat_known(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"not a medical device", response.data)
        self.assertEqual(self.client.get("/api/mats").get_json(), {"mats": []})

    def test_mat_list_marks_the_live_one(self):
        web.update(MATS, "aaa111", snapshot())
        mats = self.client.get("/api/mats").get_json()["mats"]
        self.assertEqual([(mat["id"], mat["name"], mat["live"]) for mat in mats],
                         [("aaa111", "Bed", True), ("bbb222", "bbb222", False)])
        self.assertNotIn(b"Bed", self.client.get("/").data)   # names only arrive through the API

    def test_live_mat_has_a_snapshot_and_others_do_not(self):
        web.update(MATS, "aaa111", snapshot())
        live = self.client.get("/api/mats/aaa111").get_json()
        self.assertEqual((live["live"], live["stale"], live["snapshot"]["grid"]), (True, False, [[5.0]]))
        self.assertLess(live["age_s"], 5)
        other = self.client.get("/api/mats/bbb222").get_json()
        self.assertEqual((other["live"], other["snapshot"], other["rows"]), (False, None, 20))

    def test_unknown_mat_is_a_clean_404(self):
        web.update(MATS, "aaa111", snapshot())
        for mat_id in ("nope", "aaa111x", "local"):
            response = self.client.get(f"/api/mats/{mat_id}")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.get_json(), {"error": "unknown mat"})
        # an id with slashes matches no address at all: still a plain "not found", never an error
        self.assertEqual(self.client.get("/api/mats/..%2F..%2Fetc").status_code, 404)
        self.assertEqual(self.client.get("/data").status_code, 404)   # old address is gone

    def test_old_snapshot_is_reported_stale(self):
        with mock.patch.object(web.time, "monotonic", return_value=100.0):
            web.update(MATS, "aaa111", snapshot())
        with mock.patch.object(web.time, "monotonic", return_value=100.0 + web.STALE_AFTER_S + 1):
            data = self.client.get("/api/mats/aaa111").get_json()
        self.assertTrue(data["stale"])
        self.assertAlmostEqual(data["age_s"], web.STALE_AFTER_S + 1)

    def test_snapshot_does_not_outlive_its_mat_being_live(self):
        web.update(MATS, "aaa111", snapshot(1.0))
        web.update(MATS, "bbb222", snapshot(2.0))
        self.assertIsNone(self.client.get("/api/mats/aaa111").get_json()["snapshot"])
        self.assertEqual(self.client.get("/api/mats/bbb222").get_json()["snapshot"]["grid"], [[2.0]])
        web.update(MATS)                                   # disconnected
        self.assertIsNone(self.client.get("/api/mats/bbb222").get_json()["snapshot"])
        web.update(MATS, "aaa111")                         # live but no frame yet
        data = self.client.get("/api/mats/aaa111").get_json()
        self.assertEqual((data["live"], data["snapshot"], data["stale"]), (True, None, False))


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.pressure = np.zeros(SHAPE)
        self.pressure[0, 0] = 31.239
        self.pressure[1, 1] = np.nan
        self.frame = {"pressure": self.pressure, "baseline_subtracted": np.full(SHAPE, 123.0)}
        self.monitor = IndexMonitor()

    def test_pressure_grid_with_unknown_cells(self):
        data = web.build_snapshot(self.frame, [], True, self.monitor)
        self.assertEqual((data["unit"], data["scale_max"]), ("kPa", web.PRESSURE_DISPLAY_MAX_KPA))
        self.assertEqual((len(data["grid"]), len(data["grid"][0])), SHAPE)
        self.assertEqual((data["grid"][0][0], data["grid"][1][1], data["grid"][2][2]), (31.24, None, 0.0))
        web.app.json.dumps(data)   # must be valid JSON as it stands

    def test_falls_back_to_the_relative_signal_without_calibration(self):
        self.frame["pressure"] = None
        data = web.build_snapshot(self.frame, [], None, self.monitor)
        self.assertEqual((data["unit"], data["scale_max"], data["grid"][0][0]),
                         ("relative", web.VALUE_MAX_DEFAULT, 123.0))
        self.assertIsNone(data["occupied"])

    def test_hotspots_and_patient_states(self):
        track = {"id": 3, "peak_kpa": 31.239, "cells": {(2, 5), (2, 4)}, "active_s": 42.04,
                 "persistent": True, "centroid": (2.0, 4.5)}
        data = web.build_snapshot(self.frame, [track], False, self.monitor)
        self.assertEqual(data["hotspots"], [{"id": 3, "peak_kpa": 31.2, "cells": [[2, 4], [2, 5]],
                                             "active_s": 42.0, "persistent": True}])
        self.assertIs(data["occupied"], False)

    def test_indices_report_value_threshold_and_state(self):
        data = web.build_snapshot(self.frame, [], True, self.monitor)   # nothing evaluated yet
        self.assertEqual([(item["name"], item["layer"], item["value"], item["state"]) for item in data["indices"]],
                         [("Sustained load", "map", None, "inactive"), ("Mat overview", "summary", None, "inactive")])
        self.monitor.values = {"Sustained load": np.full(SHAPE, 0.25), "Mat overview": 0.9}
        self.monitor.states = {"Sustained load": "ok", "Mat overview": "near"}
        data = web.build_snapshot(self.frame, [], True, self.monitor)
        self.assertEqual(data["indices"][0]["value"], 0.25)                # a map index reports its peak cell
        self.assertEqual(data["indices"][1], {"name": "Mat overview", "layer": "summary", "value": 0.9,
                                              "threshold": 1.0, "near": 0.8, "state": "near"})


class DesktopFeedTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        self.desktop = desktop
        for patch in (mock.patch.object(desktop, "load_mat_names", return_value={"aaa111": "Bed"}),
                      mock.patch.object(desktop, "INDEX_UPDATE_INTERVAL_S", 0.0)):
            patch.start()
            self.addCleanup(patch.stop)
        try:
            self.app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(web.update, [])
        self.addCleanup(self.app._on_close)
        self.client = web.app.test_client()

    def test_connected_source_is_published_as_the_live_local_mat(self):
        self.assertEqual(self.client.get("/api/mats").get_json(), {"mats": []})
        self.app._connect()                                # Simulated
        mats = self.client.get("/api/mats").get_json()["mats"]
        self.assertEqual([(mat["id"], mat["live"]) for mat in mats], [("local", True)])
        self.assertIn("Simulated", mats[0]["name"])
        grid = np.zeros(SHAPE)
        grid[:4, :4] = 600.0
        self.app._handle_new_frame(grid, sample_time=1)
        self.app._publish_web(force=True)
        data = self.client.get("/api/mats/local").get_json()
        self.assertEqual((data["rows"], data["cols"], data["snapshot"]["unit"]), (16, 15, "kPa"))
        self.assertEqual(data["snapshot"]["grid"][0][0], 30.0)
        self.assertEqual(len(data["snapshot"]["indices"]), 2)
        self.app._disconnect()
        self.assertEqual(self.client.get("/api/mats").get_json(), {"mats": []})

    def test_known_mqtt_mats_are_listed_by_nickname(self):
        self.app._mats = {"aaa111": (16, 15), "bbb222": (20, 12)}
        self.app._publish_web(force=True)
        mats = self.client.get("/api/mats").get_json()["mats"]
        self.assertEqual([(mat["id"], mat["name"], mat["rows"], mat["live"]) for mat in mats],
                         [("aaa111", "Bed", 16, False), ("bbb222", "bbb222", 20, False)])

    def test_address_uses_the_hostname(self):
        self.assertIn(f"http://{socket.gethostname()}.local:{web.WEB_PORT}", self.app.web_address_var.get())
        self.assertIn(f"{socket.gethostname()}.local", self.app.status_var.get())


if __name__ == "__main__":
    unittest.main()
