# このパッケージの場合

```bash
pip install -r sf-session/requirements.txt
```

## 初回

- 1. ローカルにこのフォルダを置く
- 2. 必ずこのフォルダの場所でターミナルを起動する
- 3. 以下のコマンドを順番に実行する

py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt

---

## 2回目以降、実行時

.\.venv\Scripts\Activate.ps1
py session_keeper.py

※ログインしたら、ターミナル上で Enter を押す

---

### venvに入らずに実行する場合

```
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe session_keeper.py
```

---

## ワークフロー

  session_keeper  →  dl_batch  →  file_dispatch  →  (各 Box フォルダ)
  （セッション維持）       ↓
                 CSV_STAGING_DIR
                        ↓
                  jis_to_utf8  →  utf/ サブフォルダ

  file_collect  ←  (各 Box フォルダから逆収集)



---

# 不要なファイル（キャッシュ等）をクリーンアップしたいとき

py -m clean

---

## バッチファイル
```
@echo off
cd /d %~dp0

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
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] failed to install packages
    pause
    exit /b 1
)

.venv\Scripts\python.exe dl_batch.py

if errorlevel 1 (
    echo [ERROR] script failed
    pause
    exit /b 1
)

pause
```
