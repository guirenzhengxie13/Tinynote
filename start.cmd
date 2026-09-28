@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import PySide6.QtWidgets" >nul 2>&1
    if not errorlevel 1 goto venv
)
python -c "import PySide6.QtWidgets" >nul 2>&1
if not errorlevel 1 goto python
py -3 -c "import PySide6.QtWidgets" >nul 2>&1
if not errorlevel 1 goto py
echo No Python with PySide6 was found. Run setup.cmd first.
pause
exit /b 1
:venv
".venv\Scripts\python.exe" -X utf8 "%~dp0launcher.py" %*
goto result
:python
python -X utf8 "%~dp0launcher.py" %*
goto result
:py
py -3 -X utf8 "%~dp0launcher.py" %*
:result
if errorlevel 1 (
    echo Startup failed. See .runtime\startup.log for details.
    pause
    exit /b 1
)
exit /b 0
