# PyInstaller spec: onedir, windowed. Build with build_exe.bat.
# config.py is excluded on purpose: it is user-editable and loaded from the exe's folder (see paths.py).
a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("config.example.py", ".")],
    hiddenimports=["serial.tools.list_ports_windows"],
    excludes=["config"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SmartMat", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="SmartMat")
