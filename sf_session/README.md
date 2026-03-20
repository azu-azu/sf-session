# sf-session

Salesforce レポートを **ログイン済み Chrome 経由** で export するツールキット。
API ではなく、ブラウザの export URL (`?export=1`) を使う VBA マクロの Python 移植版。

## ワークフロー

```
┌──────────────────────────────────────────────────────────┐
│ Step 1: 01_session.bat                                   │
│   Chrome 起動 → 手動ログイン → 定期 reload で維持             │
└───────────────────────┬──────────────────────────────────┘
                        │ Chrome がログイン状態を維持
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 2: 02_download.bat                                  │
│   export URL を Chrome で開く → Downloads 監視 → 移動       │
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
│   vba_* フォルダの CSV を UTF-8 BOM に変換                  │
└──────────────────────────────────────────────────────────┘
```

## スクリプト一覧

| スクリプト | 役割 |
|---|---|
| `sf_session/session_keeper.py` | Chrome をリモートデバッグモードで起動し、定期 reload でセッション維持 |
| `sf_session/dl_batch.py` | ジョブ定義に基づきバッチ export |
| `sf_session/_dl_single.py` | 内部モジュール。1 レポートの export/監視/移動。`dl_batch` から利用 |
| `sf_session/file_dispatch.py` | `reportID_*` ファイルをマクロ定義の移動先フォルダへコピー・リネーム |
| `sf_session/file_collect.py` | 各フォルダから CSV を収集して `確認実行用フォルダ/vba_YYYYMMDD_jis/` に集約 (file_dispatch の逆) |
| `sf_session/jis_to_utf8.py` | `確認実行用フォルダ/vba_*` の CSV を UTF-8 BOM に変換 → `vba_*_utf/` |
| `sf_session/macro_to_xlsx.py` | xlsm → `download_jobs.xlsx` 変換。SF API で report_name を取得して列追加 |
| `sf_session/macro_book_reader.py` | ジョブ定義 (`JobEntry`) の読み取り。xlsx 優先 → xlsm fallback |
| `sf_session/config.py` | 共通パス定数 + `read_ids_file()` + `create_sf_client()` |
| `sf_session/clean.py` | `__pycache__` / `.pyc` / `.log` 等のクリーンアップ |

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

### 1. セッション確立

```powershell
01_session.bat
# Chrome が起動 → 手動で SF にログイン → Enter
# 以降 8 分ごとに reload してセッションを維持
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

主なオプション:

```
--my-chrome     session_keeper の専用プロファイルではなく OS デフォルト Chrome を使用
--box-folder    各ジョブの src_folder_name へ直接振り分け (default: outputs_csv/ に集約)
--ids-file      ids.txt の report ID との intersection でフィルタ
--date-suffix   ファイル名に _YYYYMMDD を付与
--interval      レポート間 wait 秒 (default: 2.0)
--timeout       per-report タイムアウト秒 (default: 600)
--dry-run       実行せずジョブ一覧を表示
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

### download_jobs.xlsx (推奨)

`macro_to_xlsx.py` で xlsm から生成。`macro_book_reader.py` はこちらを優先して読む。

| 列 | 内容 |
|---|---|
| no | 連番 |
| report_id | レポート ID (SF へのハイパーリンク付き) |
| report_name | レポート名 (SF API describe で取得) |
| new_filename | リネーム後ファイル名 |
| dst_folder_name | 移動先フォルダパス |
| encode | エンコーディング |
| skip | skip フラグ |

### xlsm (fallback)

`マクロ格納フォルダ/` に配置した `.xlsm` の `SalseForce` シートから読み取り。

| 列 | 内容 |
|---|---|
| AA | No |
| AB | export URL (末尾の ID を抽出) |
| AC | リネーム後ファイル名 (空なら元名維持) |
| AD | 移動先フォルダパス |
| AE | エンコーディング (空なら Shift_JIS) |
| AG | skip フラグ (値があればスキップ) |

データは 101 行目から開始。No と URL が両方空になった行で終端。

## テスト

```bash
python -m pytest sf_session/ -v
```

## クリーンアップ

```powershell
06_clean.bat              # __pycache__, .pyc, .log, .bak 等を削除
06_clean.bat --dry-run    # 削除せず対象だけ表示
```
