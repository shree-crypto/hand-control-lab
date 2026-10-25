@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Run Setup.bat and SetupLabs.bat first.
    pause
    exit /b 1
)
:menu
cls
echo HAND CONTROL - EXPERIMENTS
echo All these modes use sandbox controls, not the Windows mouse.
echo.
echo 1 - Two-hand 3D cube
echo 2 - 3D cube with head perspective
echo 3 - Calibrated gaze and pinch
echo 4 - Air drawing
echo 5 - Air instrument with sound on Windows
echo 6 - Palm command wheel
echo 7 - Face expressions
echo 8 - RGB camera lab
echo 9 - Optional backend diagnostics
echo 0 - Exit
choice /c 1234567890 /n /m "Choose: "
if errorlevel 10 exit /b 0
if errorlevel 9 goto backends
if errorlevel 8 goto camera
if errorlevel 7 goto face
if errorlevel 6 goto gestures
if errorlevel 5 goto music
if errorlevel 4 goto draw
if errorlevel 3 goto gaze
if errorlevel 2 goto head
if errorlevel 1 goto cube
goto menu
:cube
.venv\Scripts\python.exe -m gesture_control workbench
goto done
:head
.venv\Scripts\python.exe -m gesture_control workbench --head
goto done
:gaze
.venv\Scripts\python.exe -m gesture_control gaze
goto done
:draw
.venv\Scripts\python.exe -m gesture_control draw
goto done
:music
echo Start with low speaker volume. Release pinch or hide either hand to silence.
.venv\Scripts\python.exe -m gesture_control music --audio
goto done
:gestures
.venv\Scripts\python.exe -m gesture_control gestures
goto done
:face
.venv\Scripts\python.exe -m gesture_control face
goto done
:camera
.venv\Scripts\python.exe -m gesture_control camera-lab --duration 15
goto done
:backends
.venv\Scripts\python.exe -m gesture_control backends --doctor
:done
pause
goto menu
