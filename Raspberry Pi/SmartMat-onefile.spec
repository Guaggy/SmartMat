# PyInstaller spec: onefile, windowed. Build with build_exe_onefile.bat. Keep Analysis in sync with SmartMat.spec.
# config.py is excluded on purpose: it is user-editable and loaded from paths.APP_DIR (see paths.py).
a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("config.example.py", "."), ("assets", "assets"), ("samples", "samples")],
    hiddenimports=["serial.tools.list_ports_windows"],
    excludes=["config"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SmartMat", console=False)
