"""Where the app keeps its writable files: the project folder, or (frozen) a per-user folder / the exe's folder."""

import os
import shutil
import sys
from pathlib import Path

USER_DATA = ("config.py", "mats.json", "recordings", "profiles")  # next to the exe = an older install that keeps its data there


def choose_data_dir(frozen, base_dir, local_appdata, exists):
    """(data folder, mode). base_dir = the project folder, or the exe's folder when frozen.
    Modes: source (not frozen), portable (portable.txt next to the exe), legacy (user data already next to the
    exe, or no usable LOCALAPPDATA), user (%LOCALAPPDATA%\\SmartMat)."""
    if not frozen:
        return base_dir, "source"
    if exists(base_dir / "portable.txt"):
        return base_dir, "portable"
    if any(exists(base_dir / name) for name in USER_DATA) or not local_appdata:
        return base_dir, "legacy"
    return Path(local_appdata) / "SmartMat", "user"


FROZEN = getattr(sys, "frozen", False)
_BASE_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
APP_DIR, DATA_MODE = choose_data_dir(FROZEN, _BASE_DIR, os.environ.get("LOCALAPPDATA"), Path.exists)

if FROZEN:
    if DATA_MODE == "user":
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:  # cannot create the per-user folder: keep the data next to the exe
            APP_DIR, DATA_MODE = _BASE_DIR, "legacy"
    # config.py lives in APP_DIR (user-editable); first run copies the bundled example there
    if not (APP_DIR / "config.py").exists():
        shutil.copy(Path(sys._MEIPASS) / "config.example.py", APP_DIR / "config.py")
    sys.path.insert(0, str(APP_DIR))

RESOURCE_DIR = Path(sys._MEIPASS) if FROZEN else APP_DIR  # bundled read-only data (assets/); APP_DIR is user data


def resource_path(name):
    """A file shipped with the app (not user data): next to the sources, or inside the frozen bundle"""
    return RESOURCE_DIR / name
