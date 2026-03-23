@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating venv...
    py -m venv .venv
    if errorlevel 1 (
        echo [ERROR] failed to create venv
        pause
        exit /b 1
    )
)

echo Upgrading pip...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] failed to upgrade pip
    pause
    exit /b 1
)

echo Installing packages...
.venv\Scripts\python.exe -m pip install -r sf_session\requirements.txt
if errorlevel 1 (
    echo [ERROR] failed to install packages
    pause
    exit /b 1
)

echo Setup complete.
pause
