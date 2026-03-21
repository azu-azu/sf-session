# sf-session

Salesforce レポートを **ログイン済み Chrome 経由** で export するツールキット。
API ではなく、ブラウザの export URL (`?export=1`) を使う VBA マクロの Python 移植版。

## ワークフロー

```
┌──────────────────────────────────────────────────────────┐
│ Step 1: 01_session.bat                                   │
│   Chrome 起動 → ID/PW 自動入力 → MFA 手動 → reload 維持     │
└───────────────────────┬──────────────────────────────────┘
                        │ Chrome がログイン状態を維持
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 2: 02_download.bat                                  │
│   pre-flight login check → export URL → DL 監視 → 移動    │
└───────────────────────┬──────────────────────────────────┘
                        │ reportID_*.csv が出力先に集まる
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 3: 03_dispatch.bat                                  │
│   reportID_* ファイルを Box フォルダへ振り分け・リネーム        │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 4: 04_collect.bat                                   │
│   各フォルダから CSV を収集して確認実行用フォルダに集約          │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 5: 05_convert.bat                                   │
│   *_jis/ フォルダの CSV を UTF-8 BOM に変換                  │
└──────────────────────────────────────────────────────────┘
```

## スクリプト一覧

ルート直下の `*.bat` がランチャー、`sf_session/` 以下が Python モジュール。

| スクリプト | 役割 |
|---|---|
| `sf_session/session_keeper.py` | Chrome 起動 → 自動ログイン（MFA は手動待ち）→ 定期 reload でセッション維持 |
| `sf_session/dl_batch.py` | pre-flight login check 付きバッチ export。セッション切れ時は自動復帰 |
| `sf_session/browser.py` | Chrome 起動・WebDriver 接続の共通モジュール |
| `sf_session/login_helper.py` | ログインページ検出・ID/PW 自動入力・MFA 完了待ち |
| `sf_session/file_dispatch.py` | `reportID_*` ファイルをマクロ定義の移動先フォルダへコピー・リネーム |
| `sf_session/file_collect.py` | 各フォルダから CSV を収集して `CSV_STAGING_DIR` に集約 (file_dispatch の逆) |
| `sf_session/jis_to_utf8.py` | `CSV_STAGING_DIR` 内の CSV を UTF-8 BOM に変換 → `*_utf/` |
| `sf_session/macro_to_xlsx.py` | xlsm → `download_jobs.xlsx` 変換。SF API で report_name を取得して列追加 |
| `sf_session/macro_book_reader.py` | ジョブ定義 (`JobEntry`) の読み取り。xlsm から直接読み取り |
| `sf_session/config.py` | 共通パス定数 + `read_ids_file()` + `create_sf_client()` + `get_login_credentials()` |
| `sf_session/clean.py` | `__pycache__` / `.pyc` / `.log` 等のクリーンアップ |
| `sf_session/report_filter/` | レポートのメタデータ抽出 (API 経由、データ本体は取らない) |

## セットアップ

```powershell
# venv 作成 & 依存 install
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r sf_session/requirements.txt
```

依存: `selenium`, `openpyxl`, `simple-salesforce`, `python-dotenv`

## 使い方

bat ファイルをダブルクリック、または PowerShell からオプション付きで実行。

### 起動パターン

2 通りの使い方がある。

**パターン A: session_keeper + dl_batch（推奨）**

```
01_session.bat          ← Chrome 起動 + 自動ログイン + セッション維持
02_download.bat         ← ↑ の Chrome に接続して export
```

session_keeper がセッションを維持するので、長時間の連続 export でも切れにくい。

**パターン B: dl_batch 単独**

```
02_download.bat         ← 自前で Chrome を起動 + 自動ログイン + export
```

session_keeper なしでも動く。dl_batch が専用プロファイルで Chrome を起動し、
ログインしてから export を開始する。export 完了後に Chrome は自動終了する。

### 自動ログインの仕組み

`.env` に認証情報を設定すると、ログインページで ID/PW を自動入力する。
MFA（多要素認証）が設定されている場合はユーザーが手動で完了するまで待機する。

```ini
# .env
SF_USERNAME=user@example.com        # API 用（必須）
SF_PASSWORD=password                # API 用（必須）
SF_SECURITY_TOKEN=token             # API 用

# UI ログイン用（省略時は SF_USERNAME / SF_PASSWORD を使用）
SF_LOGIN_USERNAME=ui-user@example.com
SF_LOGIN_PASSWORD=ui-password
```

ログインの flow:

```
ログイン済み → skip（即座に処理開始）
ログインページ → ID/PW 自動入力 → Login click
  → MFA ページ → 手動で完了するまで待機（timeout なし、Ctrl+C で中断可）
  → SF ホーム画面 → 処理開始
```

### 1. セッション確立

```powershell
01_session.bat
# Chrome 起動 → 自動ログイン（MFA は手動待ち）→ 8分ごとに reload
# Ctrl+C で停止
```

主なオプション:

```
--url           keep-alive 対象 URL
--interval      reload 間隔 (秒, default: 480)
--port          リモートデバッグポート (default: 9222)
--no-launch     既存 Chrome に接続 (Chrome を起動しない)
```

### 2. バッチ export

```powershell
# dry-run でジョブ一覧を確認
02_download.bat --dry-run

# 実行 (outputs_csv/ に全ファイル集約)
02_download.bat

# Box フォルダへ per-job 振り分け
02_download.bat --box-folder

# ids.txt でフィルタ
02_download.bat --ids-file

# 日付サフィックス付与
02_download.bat --date-suffix
```

起動時に pre-flight login check を行い、ログインが必要なら自動入力する。
export 中にセッションが切れた場合は、タブを走査してログインページを検出し、
自動ログイン → 1 回だけリトライする（無限ループ防止）。

主なオプション:

```
--my-chrome       OS デフォルト Chrome を使用（login check skip、手動ログイン前提）
--no-login-check  pre-flight login check を skip
--port            リモートデバッグポート (default: 9222)
--box-folder      各ジョブの src_folder_name へ直接振り分け (default: outputs_csv/ に集約)
--ids-file        ids.txt の report ID との intersection でフィルタ
--date-suffix     ファイル名に _YYYYMMDD を付与
--interval        レポート間 wait 秒 (default: 2.0)
--timeout         per-report タイムアウト秒 (default: 600)
--dry-run         実行せずジョブ一覧を表示
```

### 3. ファイル振り分け (export 後)

```powershell
# dry-run で振り分け先を確認
03_dispatch.bat --source-dir outputs_csv --dry-run

# 実行
03_dispatch.bat --source-dir outputs_csv

# 日付サフィックス + ids.txt フィルタ
03_dispatch.bat --source-dir outputs_csv --date-suffix --ids-file
```

## ids.txt — レポート ID フィルタ

`--ids-file` フラグを付けると、`ids.txt` に書かれた report ID だけを処理対象にする。

- **置き場所**: `レポートID/ids.txt`
- **フォーマット**: 1 行 1 report ID（UTF-8）
- `#` で始まる行はコメント扱いでスキップ
- 空行もスキップ

```text
# 今日の対象レポート
00O000000000001AAA
00O000000000002AAA
```

`02_download.bat` / `03_dispatch.bat` の両方で使える。

## ジョブ定義

`マクロ格納フォルダ/` に配置した `.xlsm` の `SalseForce` シートから直接読み取る。

| 列 | 内容 |
|---|---|
| AA | No |
| AB | export URL (末尾の ID を抽出) |
| AC | リネーム後ファイル名 (空なら元名維持、末尾 `_YYYYMMDD` は自動除去) |
| AD | 移動先フォルダパス |
| AE | エンコーディング (空なら Shift_JIS) |
| AG | skip フラグ (値があればスキップ) |

データは 101 行目から開始。No と URL が両方空になった行で終端。

`macro_to_xlsx.py` で xlsm → `download_jobs.xlsx` を生成することもできる（確認用）。

## レポートメタデータ抽出 (optional)

API 経由でレポートのフィルタ条件・行数・列数・オブジェクト情報を取得する。データ本体はダウンロードしない。

```powershell
py -m sf_session.report_filter
```

- 前提: `.env` に SF 認証情報、`レポートID/ids.txt` に対象 ID を記載
- 出力: `outputs_log/report_filters/` (JSON) + `pipelines/{report_id}/report_metadata.json`
- auto/manual 分類: フィルタが SOQL に自動変換可能かどうかで分類

## テスト

```bash
python -m pytest -v
```

## クリーンアップ

```powershell
06_clean.bat              # __pycache__, .pyc, .log, .bak 等を削除
06_clean.bat --dry-run    # 削除せず対象だけ表示
```
