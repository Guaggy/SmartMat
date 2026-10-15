import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import config
from processing import calibration
from processing.frames import orient_grid
from sources.serial_source import MAXRAYS_PROFILE, TEXT_PROFILE, Port, SerialSource

DEFAULT_SHAPE = (config.TOTAL_ROWS, config.TOTAL_COLS)


class FakeConnection:
    def __init__(self):
        self.data = bytearray()

    @property
    def in_waiting(self):
        return len(self.data)

    def read(self, count):
        out = bytes(self.data[:count])
        del self.data[:count]
        return out

    def close(self):
        pass


def maxrays_packet(fill):
    return b"\xA5\x5A\x01\x96" + bytes([fill]) * 400 + b"\x00\x00"


class SerialSourceTest(unittest.TestCase):
    def make(self, profile, target_fps=0, clock=None):
        source = SerialSource("COM9", profile, **({"clock": clock} if clock else {}))
        source.target_fps = target_fps  # averaging off unless a test asks for it
        source._connection = FakeConnection()
        return source

    def test_text_profile(self):
        source = self.make(TEXT_PROFILE)
        self.assertEqual(source.mat_id, "COM9")
        self.assertEqual(source.value_max, config.VALUE_MAX_DEFAULT)
        cells = source.shape[0] * source.shape[1]
        source._connection.data.extend((",".join(["500"] * cells) + "\n").encode())
        source._poll_once()
        grid = source.latest.take()
        self.assertEqual(grid.shape, source.shape)
        self.assertTrue((grid == 500).all())
        self.assertEqual(source.quality.snapshot()["valid"], 1)

    def test_maxrays_profile_in_chunks(self):
        source = self.make(MAXRAYS_PROFILE)
        self.assertEqual((source.shape, source.value_max, source.mat_id, source.baud),
                         ((20, 20), 255, "maxrays-usb", 921600))
        stream = b"\x01\x02" + maxrays_packet(255) + maxrays_packet(0)[:100]
        for i in range(0, len(stream), 17):
            source._connection.data.extend(stream[i:i + 17])
            source._poll_once()
        grid = source.latest.take()
        self.assertEqual(grid.shape, (20, 20))
        self.assertTrue((grid == 1000).all())  # 255 -> 1000
        quality = source.quality.snapshot()
        self.assertEqual((quality["valid"], quality["malformed"]), (1, 0))  # 2 leading filler bytes: not malformed
        self.assertEqual(source.serial_stats()["discarded_bytes"], 2)  # ...but still visible in diagnostics

    def test_filler_between_frames_is_not_malformed(self):
        source = self.make(MAXRAYS_PROFILE)
        source._connection.data.extend(b"\x00" * 50)  # idle bytes alone
        source._poll_once()
        source._connection.data.extend(b"\x00" * 20 + maxrays_packet(5))
        source._poll_once()
        quality = source.quality.snapshot()
        self.assertEqual((quality["valid"], quality["malformed"]), (1, 0))
        self.assertEqual(source.serial_stats()["discarded_bytes"], 70)

    def test_invalid_frame_is_malformed_but_not_when_the_poll_also_decoded_a_frame(self):
        source = self.make(MAXRAYS_PROFILE)
        bad = b"\xA5\x5A\x00\x00" + b"\x11" * 500  # false header, nothing confirms a packet
        source._connection.data.extend(bad)
        source._poll_once()
        quality = source.quality.snapshot()
        self.assertEqual((quality["valid"], quality["malformed"]), (0, 1))
        self.assertEqual(source.serial_stats()["invalid_frames"], 1)
        source._connection.data.extend(bad + maxrays_packet(7))
        source._poll_once()
        quality = source.quality.snapshot()
        self.assertEqual((quality["valid"], quality["malformed"]), (1, 1))  # no second malformed packet
        self.assertEqual(source.serial_stats()["invalid_frames"], 2)

    def test_two_frames_in_one_read_count_one_drop(self):
        source = self.make(MAXRAYS_PROFILE)
        source._connection.data.extend(maxrays_packet(10) + maxrays_packet(20) + b"\xA5\x5A")
        source._poll_once()
        self.assertEqual(source.quality.snapshot()["valid"], 2)
        self.assertEqual(source.quality.snapshot()["dropped"], 1)

    def test_default_target_rate_is_ten_for_maxrays_only(self):
        self.assertEqual(SerialSource("COM9", MAXRAYS_PROFILE).target_fps, 10)
        self.assertEqual(SerialSource("COM9", TEXT_PROFILE).target_fps, 0)

    def test_maxrays_frames_are_averaged_per_window_without_counting_drops(self):
        now = [10.0]
        source = self.make(MAXRAYS_PROFILE, target_fps=8, clock=lambda: now[0])  # 0.125 s = 8 steps of 1/64 s
        outputs = []
        for step in range(18):  # a fast stream: one frame per poll, 0..255 raw values 10 then 20
            source._connection.data.extend(maxrays_packet(10 if step < 8 else 20))
            source._poll_once()
            grid = source.latest.take()
            if grid is not None:
                outputs.append((step, grid[0, 0]))
            now[0] += 1 / 64
        self.assertEqual([step for step, _ in outputs], [8, 17])  # one grid per window, not per frame
        self.assertAlmostEqual(outputs[0][1], (8 * 10 + 20) / 9 * 1000 / 255)  # float mean of frames 0..8
        quality = source.quality.snapshot()
        self.assertEqual((quality["valid"], quality["malformed"], quality["dropped"]), (18, 0, 0))
        self.assertEqual(source._out, 2)

    def test_average_is_a_float_mean_of_the_window(self):
        now = [0.0]
        source = self.make(MAXRAYS_PROFILE, target_fps=10, clock=lambda: now[0])
        source._connection.data.extend(maxrays_packet(10) + maxrays_packet(21))
        source._poll_once()
        self.assertIsNone(source.latest.take())
        now[0] = 0.1
        source._poll_once()  # no new bytes, the window just ran out
        np.testing.assert_allclose(source.latest.take(), 15.5 * 1000 / 255)  # not rounded to a uint8
        self.assertEqual(source.serial_stats()["output_per_s"], 0.0)  # rates update at most once a second

    def test_raw_capture_writes_the_exact_bytes_and_stops_after_the_duration(self):
        source = self.make(MAXRAYS_PROFILE)
        now = [100.0]
        path = Path(tempfile.mkdtemp()) / "sub" / "raw.bin"
        source.start_raw_capture(path, seconds=5, clock=lambda: now[0])
        stream = b"" + maxrays_packet(7) + maxrays_packet(8)
        source._connection.data.extend(stream[:100])
        source._poll_once()
        source._connection.data.extend(stream[100:])
        now[0] = 104.9
        source._poll_once()
        self.assertTrue(source.capturing)
        self.assertFalse(path.exists())
        now[0] = 105.0
        source._poll_once()  # the port is quiet: the time alone ends it
        self.assertFalse(source.capturing)
        self.assertEqual(path.read_bytes(), stream)
        self.assertEqual((source.capture_result.size, source.capture_result.headers), (len(stream), 2))
        source._connection.data.extend(maxrays_packet(9))
        source._poll_once()  # nothing is written after the capture ended
        self.assertEqual(path.read_bytes(), stream)

    def test_capture_is_written_when_the_port_vanishes(self):
        source = self.make(MAXRAYS_PROFILE)
        path = Path(tempfile.mkdtemp()) / "raw.bin"
        source.start_raw_capture(path, seconds=60)
        source._connection.data.extend(maxrays_packet(7))
        source._poll_once()
        source._connection = mock.Mock()
        type(source._connection).in_waiting = mock.PropertyMock(side_effect=OSError("port gone"))
        source._running = True
        with self.assertRaises(OSError):
            source._run()
        self.assertFalse(source.capturing)
        self.assertEqual(path.read_bytes(), maxrays_packet(7))

    def test_start_asks_for_a_large_driver_buffer(self):
        with mock.patch("serial.Serial") as port:
            port.return_value.in_waiting = 0
            source = SerialSource("COM9", MAXRAYS_PROFILE)
            source.start()
            source.stop()
        port.assert_called_once_with("COM9", 921600, timeout=0)
        port.return_value.set_buffer_size.assert_called_once_with(rx_size=256 * 1024)

    def test_serial_stats(self):
        source = self.make(MAXRAYS_PROFILE)
        source._connection.data.extend(b"" + maxrays_packet(1))
        source._poll_once()
        stats = source.serial_stats()
        self.assertEqual((stats["protocol"], stats["discarded_bytes"], stats["invalid_frames"]),
                         (MAXRAYS_PROFILE, 2, 0))
        self.assertEqual(source._bytes, 408)
        self.assertIsNone(self.make(TEXT_PROFILE).serial_stats()["discarded_bytes"])


class OrientGridTests(unittest.TestCase):
    def test_rotations_and_mirrors_on_a_non_square_grid(self):
        grid = np.arange(6).reshape(2, 3)  # [[0 1 2] [3 4 5]]
        np.testing.assert_array_equal(orient_grid(grid), grid)
        np.testing.assert_array_equal(orient_grid(grid, 90), [[3, 0], [4, 1], [5, 2]])  # clockwise
        np.testing.assert_array_equal(orient_grid(grid, 180), [[5, 4, 3], [2, 1, 0]])
        np.testing.assert_array_equal(orient_grid(grid, 270), [[2, 5], [1, 4], [0, 3]])
        np.testing.assert_array_equal(orient_grid(grid, 0, mirror_h=True), [[2, 1, 0], [5, 4, 3]])
        np.testing.assert_array_equal(orient_grid(grid, 0, mirror_v=True), [[3, 4, 5], [0, 1, 2]])
        np.testing.assert_array_equal(orient_grid(grid, 90, True, True), [[2, 5], [1, 4], [0, 3]])


class DesktopSerialTests(unittest.TestCase):
    def test_port_label_protocol_and_grid_switch(self):
        from gui import desktop
        self.addCleanup(setattr, config, "TOTAL_ROWS", DEFAULT_SHAPE[0])
        self.addCleanup(setattr, config, "TOTAL_COLS", DEFAULT_SHAPE[1])
        for patch in (mock.patch.object(desktop, "list_ports",
                                        return_value=[Port("COM3", "COM3 - USB-SERIAL CH340")]),
                      mock.patch.object(SerialSource, "start"),
                      mock.patch.object(desktop, "save_mat_names"),
                      mock.patch.object(calibration, "PROFILES_DIR", Path(self.enterContext(
                          tempfile.TemporaryDirectory())))):
            patch.start()
            self.addCleanup(patch.stop)
        try:
            app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(app._on_close)
        app.source_var.set("Serial")
        app._refresh_devices()
        self.assertEqual(list(app.device_menu.cget("values")), ["COM3 - USB-SERIAL CH340"])
        self.assertEqual(app.baud_var.get(), f"Baud rate: {config.BAUD_RATE}")
        app.protocol_var.set(MAXRAYS_PROFILE)
        app.protocol_menu.event_generate("<<ComboboxSelected>>")
        app.root.update()
        self.assertEqual(app.baud_var.get(), "Baud rate: 921600")
        app._connect()
        self.assertEqual((app.source.port, app.source.mat_id), ("COM3", "maxrays-usb"))
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), (20, 20))

    def test_orientation_swaps_grid_and_capture_button_follows_source(self):
        from gui import desktop
        self.addCleanup(setattr, config, "TOTAL_ROWS", DEFAULT_SHAPE[0])
        self.addCleanup(setattr, config, "TOTAL_COLS", DEFAULT_SHAPE[1])
        patcher = mock.patch.object(desktop, "save_mat_names")
        patcher.start()
        self.addCleanup(patcher.stop)
        try:
            app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(app._on_close)
        app._connect()  # simulated, default grid
        app._update_capture_button()
        self.assertTrue(app.capture_button.instate(["disabled"]))
        app.rotation_var.set("90")
        app._orientation_changed()
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), DEFAULT_SHAPE[::-1])
        grid = app._orient(np.zeros(DEFAULT_SHAPE))  # a live frame of the mat's own size
        self.assertEqual(grid.shape, DEFAULT_SHAPE[::-1])
        app.source = SerialSource("COM9")
        app._update_capture_button()
        self.assertFalse(app.capture_button.instate(["disabled"]))
        app.source = None

    def test_auto_reconnect_keeps_retrying_until_it_works_and_disconnect_stops_it(self):
        from gui import desktop
        self.addCleanup(setattr, config, "TOTAL_ROWS", DEFAULT_SHAPE[0])
        self.addCleanup(setattr, config, "TOTAL_COLS", DEFAULT_SHAPE[1])
        now = [1000.0]
        fake_time = mock.Mock(wraps=desktop.time, time=lambda: now[0])
        start = mock.patch.object(SerialSource, "start", side_effect=[None, OSError("gone"), OSError("gone"),
                                                                      OSError("gone"), None])
        for patch in (mock.patch.object(desktop, "save_mat_names"), mock.patch.object(desktop, "time", fake_time),
                      mock.patch.object(calibration, "PROFILES_DIR", Path(self.enterContext(
                          tempfile.TemporaryDirectory())))):
            patch.start()
            self.addCleanup(patch.stop)
        try:
            app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(app._on_close)
        starts = start.start()
        self.addCleanup(start.stop)
        app.source_var.set("Serial")
        app._port_devices = {"COM9": "COM9"}
        app.device_var.set("COM9")
        app.auto_reconnect_var.set(True)
        app._connect()
        self.assertIsNotNone(app.source, app.status_var.get())
        now[0] += config.STALE_AFTER_S + 1
        app._check_connection_health()  # stale: first reconnect attempt fails
        self.assertEqual((app.source, starts.call_count), (None, 2))
        self.assertIn("reconnecting...", app.connection_var.get())
        app._retry_reconnect()  # too soon
        self.assertEqual(starts.call_count, 2)
        now[0] += config.RECONNECT_INTERVAL_S
        app._retry_reconnect()  # still unplugged: second failure keeps the loop alive
        self.assertEqual((app.source, starts.call_count), (None, 3))
        now[0] += config.RECONNECT_INTERVAL_S
        app._retry_reconnect()
        self.assertEqual((app.source, starts.call_count), (None, 4))
        now[0] += config.RECONNECT_INTERVAL_S
        app._retry_reconnect()  # replugged
        self.assertIsNotNone(app.source)
        self.assertEqual(starts.call_count, 5)
        # a manual Disconnect after a failed attempt stops the retries
        starts.side_effect = OSError("gone")
        now[0] += config.STALE_AFTER_S + 1
        app._check_connection_health()
        self.assertIsNone(app.source)
        calls = starts.call_count
        app._disconnect()
        now[0] += config.RECONNECT_INTERVAL_S * 3
        app._retry_reconnect()
        self.assertEqual(starts.call_count, calls)


if __name__ == "__main__":
    unittest.main()
