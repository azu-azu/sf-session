@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Run 00_setup.bat first.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m sf_session.download --ids-file %*
pause
