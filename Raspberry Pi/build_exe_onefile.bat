@echo off
rem Build dist\onefile\SmartMat.exe (PyInstaller onefile, windowed). Leaves dist\SmartMat\ and dist\SmartMat.zip alone.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Create the venv first: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt pyinstaller & exit /b 1)
.venv\Scripts\python -m PyInstaller --noconfirm --log-level WARN --distpath dist\onefile SmartMat-onefile.spec || exit /b 1
echo Built dist\onefile\SmartMat.exe
