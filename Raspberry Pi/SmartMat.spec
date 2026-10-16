# PyInstaller spec: onedir, windowed. Build with build_exe.bat.
# config.py is excluded on purpose: it is user-editable and loaded from paths.APP_DIR (see paths.py).
a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("config.example.py", "."), ("assets", "assets"), ("samples", "samples")],
    hiddenimports=["serial.tools.list_ports_windows"],
    excludes=["config"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SmartMat", console=False,
          icon="assets/icon.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="SmartMat")
