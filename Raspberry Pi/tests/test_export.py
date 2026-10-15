"""CSV export: snapshot (long), recording (wide), and the snapshot/recording buttons."""

import csv
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import config
from processing.export import SNAPSHOT_COLUMNS, recording_to_csv, snapshot_rows, write_snapshot_csv


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.reader(file))


def small_frame(pressure=True):
    raw = np.array([[10.0, 20.0, 30.0], [40.0, np.nan, 60.0]])
    return {"raw": raw, "baseline_subtracted": raw - 5.0,
            "pressure": raw / 10.0 if pressure else None}


class SnapshotTests(unittest.TestCase):
    def test_one_row_per_cell_with_empty_for_nan(self):
        rows = snapshot_rows(small_frame(), 1_700_000_000.0, "mat-a")
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0][1:], ["mat-a", 0, 0, 10.0, 5.0, 1.0])
        self.assertEqual(rows[4][2:], [1, 1, "", "", ""])      # the NaN cell
        self.assertTrue(rows[0][0].startswith("2023-11-1"))    # ISO timestamp

    def test_pressure_is_empty_without_calibration(self):
        rows = snapshot_rows(small_frame(pressure=False), 1.0)
        self.assertEqual({row[6] for row in rows}, {""})
        self.assertEqual(rows[1][4], 20.0)

    def test_csv_file_has_the_documented_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snap.csv"
            self.assertEqual(write_snapshot_csv(path, small_frame(), 1.0, None), 6)
            table = read_csv(path)
        self.assertEqual(tuple(table[0]), SNAPSHOT_COLUMNS)
        self.assertIn("raw_scaled_0_1000", table[0])
        self.assertEqual(table[1][1:], ["", "0", "0", "10.0", "5.0", "1.0"])
        self.assertEqual(table[5][4:], ["", "", ""])


class RecordingTests(unittest.TestCase):
    def write(self, folder, **changes):
        session = {"format": "smartmat_raw_v1", "grid_shape": [2, 3], "metadata": {}, "events": [],
                   "frames": [{"timestamp": 100.0, "raw": [[1, 2, 3], [4, None, 6]]},
                              {"timestamp": 100.5, "raw": [[7, 8, 9], [10, 11, 12]]}]}
        session.update(changes)
        path = Path(folder) / "rec.json"
        path.write_text(json.dumps(session), encoding="utf-8")
        return path, Path(folder) / "rec.csv"

    def test_wide_csv_row_major_values_as_stored(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = self.write(folder)
            self.assertEqual(recording_to_csv(source, target), 2)
            table = read_csv(target)
        self.assertEqual(table[0], ["timestamp_iso", "elapsed_s", "r00_c00", "r00_c01", "r00_c02",
                                   "r01_c00", "r01_c01", "r01_c02"])
        self.assertEqual(table[1][1:], ["0.0", "1.0", "2.0", "3.0", "4.0", "", "6.0"])
        self.assertEqual(table[2][1:], ["0.5", "7.0", "8.0", "9.0", "10.0", "11.0", "12.0"])

    def test_other_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = self.write(folder, format="something_else")
            with self.assertRaises(ValueError):
                recording_to_csv(source, target)


class DesktopExportTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        self.desktop = desktop
        try:
            self.app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)

    def test_no_frame_explains_instead_of_opening_a_dialog(self):
        with mock.patch.object(self.desktop.filedialog, "asksaveasfilename") as dialog:
            self.app._export_snapshot()
        dialog.assert_not_called()
        self.assertIn("No frame yet", self.app.status_var.get())

    def test_snapshot_writes_csv_and_png_with_the_same_base_name(self):
        self.app._handle_new_frame(np.full((config.TOTAL_ROWS, config.TOTAL_COLS), 100.0), sample_time=1.0)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "snap.csv")
            with mock.patch.object(self.desktop.filedialog, "asksaveasfilename", return_value=path):
                self.app._export_snapshot()
            table = read_csv(path)
            self.assertTrue((Path(folder) / "snap.png").stat().st_size > 0)
        self.assertEqual(len(table), 1 + config.TOTAL_ROWS * config.TOTAL_COLS)
        self.assertIn("snap.png", self.app.status_var.get())


if __name__ == "__main__":
    unittest.main()
