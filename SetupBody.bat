@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Run Setup.bat first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe tools\download_model.py --pose
if errorlevel 1 (
    echo Body model download failed. Check the error above.
    pause
    exit /b 1
)
echo Body pose model ready. Run FourLimb.bat.
pause
