import sys

import paths  # must run first: frozen builds load config.py from paths.APP_DIR

def selftest():
    """Headless smoke test of a frozen build: `SmartMat.exe --selftest` writes selftest.txt into paths.APP_DIR."""
    import branding
    import config
    import general
    from processing.recording import RECORDINGS_DIR
    from server.alerts import AlertManager
    from server.app import create_app
    from server.store import Store
    RECORDINGS_DIR.mkdir(exist_ok=True)
    general.save_mat_names(general.load_mat_names())
    store = Store(paths.APP_DIR / "selftest.db")   # the server's own app, in process: no port needed
    try:
        health = create_app(store, AlertManager(), {}).test_client().get("/api/health").get_json()
    finally:
        store.close()
        (paths.APP_DIR / "selftest.db").unlink(missing_ok=True)
    (paths.APP_DIR / "selftest.txt").write_text(
        f"version={branding.VERSION}\nfrozen={paths.FROZEN}\napp_dir={paths.APP_DIR}\nmode={paths.DATA_MODE}\n"
        f"config={config.__file__}\nmats={general.MATS_FILE}\n"
        f"recordings={RECORDINGS_DIR}\nserver /api/health={health}\n", encoding="utf-8")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--server" in sys.argv:  # headless: same as python -m server (no tkinter)
        from server.__main__ import main as server_main
        return server_main([arg for arg in sys.argv[1:] if arg != "--server"])
    from gui.desktop import DesktopApp
    app = DesktopApp()
    app.run()

# only start if valid
if __name__ == "__main__":
    main()
