@echo off
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

REM requires-python >= 3.12 チェック
for /f "tokens=2 delims= " %%v in ('py --version 2^>^&1') do set PY_VER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% LSS 3 (
    echo [ERROR] Python 3.12 以上が必要です。現在: %PY_VER%
    pause
    exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 12 (
    echo [ERROR] Python 3.12 以上が必要です。現在: %PY_VER%
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

echo Setup complete.
pause
