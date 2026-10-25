@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3.12 -m venv .venv
    if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install --timeout 30 --retries 1 -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe tools\download_model.py
if errorlevel 1 goto failed
echo Setup complete. Run Preview.bat first.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.12 x64 from python.org with the Python launcher, then retry.
echo If Python is installed, check the error above for network or dependency problems.
pause
exit /b 1
