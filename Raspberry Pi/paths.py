"""Where the app keeps its writable files: the project folder, or the exe's folder when frozen."""

import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent

if FROZEN:
    # config.py lives next to the exe (user-editable); first run copies the bundled example there
    if not (APP_DIR / "config.py").exists():
        shutil.copy(Path(sys._MEIPASS) / "config.example.py", APP_DIR / "config.py")
    sys.path.insert(0, str(APP_DIR))
