import sys

import paths  # must run first: frozen builds load config.py from the exe folder
from gui.desktop import DesktopApp

def selftest():
    """Headless smoke test of a frozen build: `SmartMat.exe --selftest` writes selftest.txt next to the exe."""
    import config
    import general
    from gui import web
    from processing.recording import RECORDINGS_DIR
    from urllib.request import urlopen
    RECORDINGS_DIR.mkdir(exist_ok=True)
    general.save_mat_names(general.load_mat_names())
    server = web.WebServer()
    server.start()
    try:
        api = urlopen(f"http://127.0.0.1:{config.WEB_PORT}/api/mats", timeout=5).read().decode()
    finally:
        server.stop()
    (paths.APP_DIR / "selftest.txt").write_text(
        f"frozen={paths.FROZEN}\nconfig={config.__file__}\nmats={general.MATS_FILE}\n"
        f"recordings={RECORDINGS_DIR}\nweb /api/mats={api}\n", encoding="utf-8")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    app = DesktopApp()
    app.run()

# only start if valid
if __name__ == "__main__":
    main()
