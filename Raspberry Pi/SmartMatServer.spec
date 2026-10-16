# PyInstaller spec: the headless server, onedir, no console. Build: pyinstaller SmartMatServer.spec
# -> dist\SmartMatServer\SmartMatServer.exe. Same rules as SmartMat.spec: config.py stays out of the bundle
# and is loaded from paths.APP_DIR. No GUI: tkinter and matplotlib are left out.
a = Analysis(
    ["server/__main__.py"],
    pathex=["."],
    datas=[("config.example.py", "."), ("assets", "assets"), ("samples/seat_take1.json", "samples"),
           ("server/static", "server/static")],
    hiddenimports=["serial.tools.list_ports_windows", "server.app", "server.engine", "server.store",
                   "server.alerts"],
    excludes=["config", "tkinter", "matplotlib", "gui"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SmartMatServer", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="SmartMatServer")
