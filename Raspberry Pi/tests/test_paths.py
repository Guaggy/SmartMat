"""paths.choose_data_dir: where the app keeps user data (pure, so no freezing needed)."""

import unittest
from pathlib import Path

from paths import choose_data_dir

EXE = Path("C:/Apps/SmartMat")
LOCAL = "C:/Users/x/AppData/Local"


def choose(frozen=True, present=(), local=LOCAL):
    return choose_data_dir(frozen, EXE, local, lambda p: p in {EXE / name for name in present})


class ChooseDataDirTest(unittest.TestCase):
    def test_source_tree_unchanged(self):
        self.assertEqual(choose(frozen=False, present=("portable.txt",)), (EXE, "source"))

    def test_portable_flag_wins(self):
        self.assertEqual(choose(present=("portable.txt", "profiles")), (EXE, "portable"))

    def test_legacy_when_user_data_next_to_exe(self):
        for name in ("config.py", "mats.json", "recordings", "profiles"):
            self.assertEqual(choose(present=(name,)), (EXE, "legacy"), name)

    def test_user_folder_by_default(self):
        self.assertEqual(choose(), (Path(LOCAL) / "SmartMat", "user"))

    def test_missing_localappdata_falls_back_to_exe_folder(self):
        for local in (None, ""):
            self.assertEqual(choose(local=local), (EXE, "legacy"))


if __name__ == "__main__":
    unittest.main()
