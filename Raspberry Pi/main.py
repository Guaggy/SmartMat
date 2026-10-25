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

def parse_args(argv):
    """(known options, the rest). add_help is off so that `--server --help` reaches the server's own help."""
    import argparse
    parser = argparse.ArgumentParser(
        prog="main.py", add_help=False, allow_abbrev=False,
        description="SmartMat desktop app. With no option it opens the app window.",
        epilog="With --server, every other option goes to the server (same as python -m server); try: main.py --server --help")
    parser.add_argument("-h", "--help", action="store_true", help="show this help and exit")
    parser.add_argument("--selftest", action="store_true", help="headless smoke test of a frozen build; writes selftest.txt")
    parser.add_argument("--server", action="store_true", help="run the headless server instead of the app (no tkinter)")
    args, rest = parser.parse_known_args(argv)
    return parser, args, rest


def main(argv=None):
    parser, args, rest = parse_args(sys.argv[1:] if argv is None else argv)
    if args.server:
        from server.__main__ import main as server_main
        return server_main(rest + (["--help"] if args.help else []))
    if args.help:
        parser.print_help()
        return 0
    if args.selftest:
        return selftest()
    from gui.desktop import DesktopApp
    app = DesktopApp()
    app.run()

# only start if valid
if __name__ == "__main__":
    main()
