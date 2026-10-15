@echo off
rem Build dist\SmartMat\SmartMat.exe (PyInstaller onedir, windowed) and zip it to dist\SmartMat.zip.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Create the venv first: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt pyinstaller & exit /b 1)
.venv\Scripts\python -m PyInstaller --noconfirm --log-level WARN SmartMat.spec || exit /b 1
if exist dist\SmartMat.zip del dist\SmartMat.zip
tar -a -c -f dist\SmartMat.zip -C dist SmartMat || exit /b 1
echo Built dist\SmartMat\SmartMat.exe and dist\SmartMat.zip
