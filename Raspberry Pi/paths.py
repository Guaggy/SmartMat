"""Where the app keeps its writable files: the project folder, or (frozen) a per-user folder / the exe's folder."""

import os
import shutil
import sys
import tempfile
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


def config_dir(app_dir, example):
    """The folder that holds config.py: app_dir (the example is copied there on first run), or, when app_dir
    is not writable (exe folder in Program Files), a fresh temp folder with the example so the app uses defaults."""
    if (app_dir / "config.py").exists():
        return app_dir
    try:
        shutil.copy(example, app_dir / "config.py")
        return app_dir
    except OSError:
        fallback = Path(tempfile.mkdtemp(prefix="smartmat_cfg_"))
        shutil.copy(example, fallback / "config.py")
        return fallback


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
    sys.path.insert(0, str(config_dir(APP_DIR, Path(sys._MEIPASS) / "config.example.py")))

RESOURCE_DIR = Path(sys._MEIPASS) if FROZEN else APP_DIR  # bundled read-only data (assets/); APP_DIR is user data


def resource_path(name):
    """A file shipped with the app (not user data): next to the sources, or inside the frozen bundle"""
    return RESOURCE_DIR / name


def fill_config_defaults(example=None):
    """Add any setting the user's config.py lacks (an older copy) from config.example.py, so a new release never
    fails to import because of a newly added setting. Existing user values are never touched."""
    import importlib.util
    try:
        import config
    except ImportError:  # no config.py yet (source checkout before the first copy)
        return
    example = Path(example) if example else resource_path("config.example.py")
    if not example.exists():
        return
    spec = importlib.util.spec_from_file_location("_config_example", example)
    defaults = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(defaults)
    for name, value in vars(defaults).items():
        if name.isupper() and not hasattr(config, name):
            setattr(config, name, value)


fill_config_defaults()
