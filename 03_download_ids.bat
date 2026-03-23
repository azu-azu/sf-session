@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] 初回設定が必要です。setup バッチを実行してください。
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m sf_session.dl_batch --ids-file %*
pause
