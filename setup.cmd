@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo TinyNote is ready. Double-click start.cmd to run.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.10 or newer and check your network.
pause
exit /b 1
