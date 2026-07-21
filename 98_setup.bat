@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".env" (
    if exist "env.txt" (
        ren "env.txt" ".env"
        echo Renamed env.txt to .env
    ) else (
        echo [ERROR] .env file is required. Create .env or env.txt in %~dp0
        pause
        exit /b 1
    )
)

echo Python version:
py --version

py _check_python.py
if errorlevel 1 (
    pause
    exit /b 1
)

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
.venv\Scripts\python.exe -m pip install -e .
if errorlevel 1 (
    echo [ERROR] failed to install packages
    pause
    exit /b 1
)

echo Checking pipelines...
.venv\Scripts\python.exe -m sf_session.init_pipeline --ensure
if errorlevel 1 (
    echo [WARN] pipeline check failed, continuing setup...
)

echo Refreshing bat files...
.venv\Scripts\python.exe -m sf_session.init_pipeline --regen-bats
if errorlevel 1 (
    echo [WARN] bat regeneration failed, continuing setup...
)

echo Setup complete.
pause
