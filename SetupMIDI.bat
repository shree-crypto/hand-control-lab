@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Run Setup.bat first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m pip install --timeout 30 --retries 1 -r requirements-midi.txt
if errorlevel 1 (
    echo MIDI dependency installation failed. Check the error above.
    pause
    exit /b 1
)
echo MIDI ready. See docs\midi-production.md for FL Studio and loopMIDI setup.
.venv\Scripts\python.exe -m gesture_control drums --list-ports
pause
