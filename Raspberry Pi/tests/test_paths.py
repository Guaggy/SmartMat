"""paths.choose_data_dir: where the app keeps user data (pure, so no freezing needed)."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paths
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


class ConfigDirTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.example = self.root / "config.example.py"
        self.example.write_text("broker_host = 'localhost'\n", encoding="utf-8")
        self.app_dir = self.root / "app"
        self.app_dir.mkdir()

    def test_first_run_copies_example_into_app_dir(self):
        self.assertEqual(paths.config_dir(self.app_dir, self.example), self.app_dir)
        self.assertTrue((self.app_dir / "config.py").exists())

    def test_existing_config_is_left_alone(self):
        (self.app_dir / "config.py").write_text("mine = 1\n", encoding="utf-8")
        self.assertEqual(paths.config_dir(self.app_dir, self.example), self.app_dir)
        self.assertEqual((self.app_dir / "config.py").read_text(encoding="utf-8"), "mine = 1\n")

    def test_read_only_app_dir_falls_back_to_temp_folder(self):
        real_copy = shutil.copy

        def copy(src, dst):
            if Path(dst).parent == self.app_dir:
                raise PermissionError("read-only")
            return real_copy(src, dst)

        made = []
        real_mkdtemp = tempfile.mkdtemp
        with mock.patch.object(paths.shutil, "copy", copy),                 mock.patch.object(paths.tempfile, "mkdtemp",
                                  lambda **kw: made.append(real_mkdtemp(dir=self.root, **kw)) or made[-1]):
            result = paths.config_dir(self.app_dir, self.example)
        self.assertEqual(result, Path(made[0]))
        self.assertNotEqual(result, self.app_dir)
        self.assertTrue((result / "config.py").exists())
        self.assertFalse((self.app_dir / "config.py").exists())


if __name__ == "__main__":
    unittest.main()


class FillConfigDefaultsTests(unittest.TestCase):
    def test_missing_setting_is_added_and_existing_one_is_kept(self):
        import config
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            example = Path(folder) / "config.example.py"
            example.write_text("TOTAL_ROWS = 999\nBRAND_NEW_SETTING = 7\n", encoding="utf-8")
            had_rows = config.TOTAL_ROWS
            try:
                paths.fill_config_defaults(example)
                self.assertEqual(config.BRAND_NEW_SETTING, 7)
                self.assertEqual(config.TOTAL_ROWS, had_rows)  # the user's value wins
            finally:
                if hasattr(config, "BRAND_NEW_SETTING"):
                    del config.BRAND_NEW_SETTING
