"""Multi-mat MQTT: live grid shape, meta handshake, nickname registry, device list."""

import json
import tempfile
import tkinter as tk
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import config
from general import (LatestFrame, load_mat_names, mat_labels, parse_frame_text_with_reason,
                     save_mat_names)
from processing.calibration import IndividualCalibration
from processing.recording import RECORDINGS_DIR, Recorder, load_session
from processing.sensor_health import SensorHealth
from processing.source_quality import SourceQuality
from processing.temporal import TemporalAnalysis
from sources import mqtt_source
from sources.mqtt_source import MqttSource, parse_meta

DEFAULT_SHAPE = (config.TOTAL_ROWS, config.TOTAL_COLS)


def use_shape(test, rows, cols):
    """Overwrite the grid size the way the GUI does, and put it back after the test"""
    test.addCleanup(setattr, config, "TOTAL_ROWS", DEFAULT_SHAPE[0])
    test.addCleanup(setattr, config, "TOTAL_COLS", DEFAULT_SHAPE[1])
    config.TOTAL_ROWS, config.TOTAL_COLS = rows, cols


class GridShapeTests(unittest.TestCase):
    def test_consumers_read_an_overwritten_shape(self):
        use_shape(self, 20, 12)
        grid, reason = parse_frame_text_with_reason(",".join(["5"] * 240))
        self.assertIsNone(reason)
        self.assertEqual(grid.shape, (20, 12))
        self.assertEqual(TemporalAnalysis().exposure.shape, (20, 12))
        self.assertEqual(SensorHealth().states.shape, (20, 12))
        calibration = IndividualCalibration.default()
        self.assertTrue(calibration.is_calibrated(19, 11))
        self.assertEqual(calibration.apply(grid).shape, (20, 12))

    def test_frame_of_the_old_size_is_rejected(self):
        use_shape(self, 10, 8)
        self.assertEqual(parse_frame_text_with_reason(",".join(["5"] * 240))[1], "grid_size")
        self.assertIsNone(parse_frame_text_with_reason(",".join(["5"] * 80))[1])

    def test_recording_keeps_the_shape_it_was_made_with(self):
        use_shape(self, 20, 12)
        recorder = Recorder("multi_mat_shape_test")
        recorder.add_frame(np.full((20, 12), 7.0), timestamp=1.0)
        path = recorder.save()
        self.addCleanup(path.unlink)
        self.assertEqual(load_session(path)[0].shape, (20, 12))
        config.TOTAL_ROWS, config.TOTAL_COLS = DEFAULT_SHAPE
        with self.assertRaises(ValueError):
            load_session(path)


def make_source(chip_id=None):
    with mock.patch.object(mqtt_source, "mqtt"):  # no real paho client, no network
        return MqttSource(chip_id)


def message(topic, text):
    return types.SimpleNamespace(topic=topic, payload=text.encode("ascii"))


def connect(source, failed=False):
    source._on_connect(source._client, None, None, types.SimpleNamespace(is_failure=failed))


class MetaParsingTests(unittest.TestCase):
    def test_valid_payload(self):
        self.assertEqual(parse_meta("a1b2c3d4e5f6,16,15"), ("a1b2c3d4e5f6", 16, 15))
        self.assertEqual(parse_meta(" a1b2 , 20 ,12\n"), ("a1b2", 20, 12))

    def test_malformed_payloads(self):
        for text in ("", "a1b2", "a1b2,16", "a1b2,16,15,1", "a1b2,x,15", "a1b2,16,1.5",
                     "a1b2,0,15", "a1b2,16,-1", "a1b2,16,999", ",16,15",
                     "a/b,16,15", "+,16,15", "#,16,15"):
            with self.subTest(text=text):
                self.assertIsNone(parse_meta(text))


class MqttSourceTests(unittest.TestCase):
    def test_discovery_lists_every_mat_with_valid_meta(self):
        source = make_source()
        connect(source)
        source._client.subscribe.assert_called_once_with("smartmat/+/meta")
        source._on_message(None, None, message("smartmat/aaa111/meta", "aaa111,16,15"))
        source._on_message(None, None, message("smartmat/bbb222/meta", "bbb222,20,12"))
        source._on_message(None, None, message("smartmat/ccc333/meta", "garbage"))
        source._on_message(None, None, message("smartmat/ddd444/meta", "eee555,16,15"))  # id mismatch
        self.assertEqual(source.mats, {"aaa111": (16, 15), "bbb222": (20, 12)})
        self.assertEqual(source.state, "ready")

    def test_selected_mat_goes_connecting_awaiting_meta_ready(self):
        source = make_source("bbb222")
        self.assertEqual(source.state, "connecting")
        connect(source)
        self.assertEqual([call.args[0] for call in source._client.subscribe.call_args_list],
                         ["smartmat/+/meta", "smartmat/bbb222/frame"])
        self.assertEqual(source.state, "awaiting_meta")
        self.assertIsNone(source.shape)
        source._on_message(None, None, message("smartmat/aaa111/meta", "aaa111,16,15"))
        self.assertEqual(source.state, "awaiting_meta")
        source._on_message(None, None, message("smartmat/bbb222/meta", "bbb222,20,12"))
        self.assertEqual(source.state, "ready")
        self.assertEqual(source.shape, (20, 12))

    def test_refused_connection_does_not_subscribe(self):
        source = make_source("bbb222")
        connect(source, failed=True)
        source._client.subscribe.assert_not_called()
        self.assertEqual(source.state, "connecting")

    def test_frames_wait_until_the_app_uses_the_mats_shape(self):
        source = make_source("bbb222")
        connect(source)
        frame = message("smartmat/bbb222/frame", ",".join(["5"] * 240))
        source._on_message(None, None, frame)  # before meta
        source._on_message(None, None, message("smartmat/bbb222/meta", "bbb222,20,12"))
        source._on_message(None, None, frame)  # meta known, app still on 16x15: same 240 values
        self.assertIsNone(source.latest.take())
        self.assertEqual(source.quality.snapshot()["received"], 0)
        use_shape(self, 20, 12)
        source._on_message(None, None, frame)
        self.assertEqual(source.latest.take().shape, (20, 12))
        source._on_message(None, None, message("smartmat/bbb222/frame", "1,2,3"))
        self.assertEqual(source.quality.snapshot()["unexpected_grid_size"], 1)

    def test_start_fails_clearly_when_meta_never_arrives(self):
        source = make_source("bbb222")
        with mock.patch.object(mqtt_source, "META_TIMEOUT_S", 0.01):
            with self.assertRaisesRegex(TimeoutError, "no metadata from mat bbb222"):
                source.start()
        source._client.loop_stop.assert_called_once()
        source._client.disconnect.assert_called_once()

    def test_start_returns_once_meta_is_in(self):
        source = make_source("bbb222")
        source._on_message(None, None, message("smartmat/bbb222/meta", "bbb222,20,12"))
        source.start()
        source._client.connect.assert_called_once_with(config.broker_host, config.broker_port)
        source._client.loop_stop.assert_not_called()

    def test_discovery_start_never_blocks_on_the_broker(self):
        source = make_source()
        source.start()
        source._client.connect_async.assert_called_once_with(config.broker_host, config.broker_port)
        source._client.connect.assert_not_called()


class MatNamesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "mats.json"

    def test_names_survive_a_restart(self):
        save_mat_names({"aaa111": "Wheelchair"}, self.path)
        self.assertEqual(load_mat_names(self.path), {"aaa111": "Wheelchair"})

    def test_missing_corrupt_or_wrong_file_means_no_names(self):
        self.assertEqual(load_mat_names(self.path), {})
        for text in ("{not json", '["aaa111"]', ""):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                self.assertEqual(load_mat_names(self.path), {})

    def test_labels_use_nickname_else_chip_id(self):
        self.assertEqual(mat_labels({"bbb222": (20, 12), "aaa111": (16, 15)}, {"bbb222": "Bed"}),
                         {"aaa111": "aaa111", "Bed": "bbb222"})

    def test_duplicate_nicknames_stay_selectable(self):
        self.assertEqual(mat_labels(["aaa111", "bbb222"], {"aaa111": "Bed", "bbb222": "Bed"}),
                         {"Bed": "aaa111", "Bed (bbb222)": "bbb222"})


class FakeMqttSource:
    """Stands in for MqttSource so the GUI tests need no broker"""

    mats = {"aaa111": (20, 12), "bbb222": (16, 15)}

    def __init__(self, chip_id=None):
        self.chip_id = chip_id
        self.latest = LatestFrame()
        self.quality = SourceQuality()
        self.shape = self.mats.get(chip_id)

    def start(self):
        pass

    def stop(self):
        pass


class DesktopMatTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        self.desktop = desktop
        for patch in (mock.patch.object(desktop, "MqttSource", FakeMqttSource),
                      mock.patch.object(desktop, "load_mat_names", return_value={"bbb222": "Bed"}),
                      mock.patch.object(desktop, "save_mat_names")):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(setattr, config, "TOTAL_ROWS", DEFAULT_SHAPE[0])
        self.addCleanup(setattr, config, "TOTAL_COLS", DEFAULT_SHAPE[1])
        try:
            self.app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)

    def show_mats(self):
        self.app.source_var.set("MQTT")
        self.app._refresh_devices()
        self.app._sync_mats()

    def test_mqtt_devices_are_listed_by_nickname_or_chip_id(self):
        self.show_mats()
        self.assertEqual(list(self.app.device_menu.cget("values")), ["aaa111", "Bed"])
        self.assertEqual(self.app.device_var.get(), "aaa111")

    def test_rename_relabels_at_once_and_is_saved(self):
        self.show_mats()
        with mock.patch.object(self.desktop.simpledialog, "askstring", return_value=" Chair "):
            self.app._rename_mat()
        self.assertEqual(list(self.app.device_menu.cget("values")), ["Chair", "Bed"])
        self.assertEqual(self.app.device_var.get(), "Chair")
        self.desktop.save_mat_names.assert_called_once_with({"bbb222": "Bed", "aaa111": "Chair"})

    def test_connecting_to_a_mat_switches_the_grid_and_back(self):
        self.show_mats()
        self.app._connect()
        self.assertEqual(self.app.source.chip_id, "aaa111")
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), (20, 12))
        self.assertEqual(self.app.temporal.exposure.shape, (20, 12))
        self.assertEqual(self.app.sensor_health.states.shape, (20, 12))
        self.assertTrue(self.app.pressure_calibration.is_calibrated(19, 11))
        self.assertEqual(self.app.grid_info_var.get(), "Grid: 20 x 12")
        self.app._handle_new_frame(np.full((20, 12), 10.0), sample_time=1)
        self.assertEqual(self.app.frame["pressure"].shape, (20, 12))
        self.app._update_plot()

        self.app.source_var.set("Simulated")
        self.app._refresh_devices()
        self.app._connect()
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), DEFAULT_SHAPE)
        self.assertIsNone(self.app.frame)
        self.app._handle_new_frame(np.full(DEFAULT_SHAPE, 10.0), sample_time=1)
        self.assertEqual(self.app.frame["pressure"].shape, DEFAULT_SHAPE)

    def test_connect_without_a_mat_says_so(self):
        with mock.patch.object(FakeMqttSource, "mats", {}):
            self.show_mats()
            self.app._connect()
        self.assertIsNone(self.app.source)
        self.assertIn("no mat selected", self.app.status_var.get())
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), DEFAULT_SHAPE)

    def test_recording_is_saved_before_the_grid_changes(self):
        self.app._handle_new_frame(np.full(DEFAULT_SHAPE, 10.0), sample_time=1)
        self.app.recorder = Recorder("multi_mat_switch_test")
        self.app.recorder.add_frame(self.app.raw_grid, timestamp=1)
        self.app._apply_grid_shape(20, 12)
        self.assertIsNone(self.app.recorder)
        saved = list(RECORDINGS_DIR.glob("multi_mat_switch_test_*.json"))
        self.assertEqual(len(saved), 1)
        self.addCleanup(saved[0].unlink)
        self.assertEqual(json.loads(saved[0].read_text())["grid_shape"], list(DEFAULT_SHAPE))


if __name__ == "__main__":
    unittest.main()
