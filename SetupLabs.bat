@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Run Setup.bat first, then run this file.
    pause
    exit /b 1
)
.venv\Scripts\python.exe tools\download_model.py --face
if errorlevel 1 (
    echo Model setup failed. Check the message above and internet connection.
    pause
    exit /b 1
)
echo Labs models ready. Run Labs.bat.
pause
