import tkinter as tk
import unittest
from unittest import mock

import config
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
    def make(self, profile):
        source = SerialSource("COM9", profile)
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
        self.assertEqual((quality["valid"], quality["malformed"]), (1, 1))  # 2 leading garbage bytes

    def test_two_frames_in_one_read_count_one_drop(self):
        source = self.make(MAXRAYS_PROFILE)
        source._connection.data.extend(maxrays_packet(10) + maxrays_packet(20) + b"\xA5\x5A")
        source._poll_once()
        self.assertEqual(source.quality.snapshot()["valid"], 2)
        self.assertEqual(source.quality.snapshot()["dropped"], 1)


class DesktopSerialTests(unittest.TestCase):
    def test_port_label_protocol_and_grid_switch(self):
        from gui import desktop
        self.addCleanup(setattr, config, "TOTAL_ROWS", DEFAULT_SHAPE[0])
        self.addCleanup(setattr, config, "TOTAL_COLS", DEFAULT_SHAPE[1])
        for patch in (mock.patch.object(desktop, "list_ports",
                                        return_value=[Port("COM3", "COM3 - USB-SERIAL CH340")]),
                      mock.patch.object(SerialSource, "start"),
                      mock.patch.object(desktop, "save_mat_names")):
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


if __name__ == "__main__":
    unittest.main()
