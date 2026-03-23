@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] ����ݒ肪�K�v�ł��Bsetup �o�b�`�����s���Ă��������B
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m sf_session.download --retry %*
pause
