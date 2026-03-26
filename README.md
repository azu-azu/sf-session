# sf-session

Salesforce レポートを **ログイン済み Chrome 経由** で export するツールキット。
API ではなく、ブラウザの export URL (`?export=1`) を使う VBA マクロの Python 移植版。

## ワークフロー

```
┌──────────────────────────────────────────────────────────┐
│ Step 0: ■00_keep_session.bat                              │
│   Chrome 起動 → SSO/MFA 手動ログイン → reload 維持            │
└───────────────────────┬──────────────────────────────────┘
                        │ Chrome がログイン状態を維持
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 1: ★01_download.bat                             │
│   営業日チェック → login check → export URL → DL 監視 → 移動 │
└───────────────────────┬──────────────────────────────────┘
                        │ reportID_*.csv が出力先に集まる
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 2: ★02_振り分け.bat                                  │
│   reportID_* ファイルを Box フォルダへ振り分け・リネーム        │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 3: py -m sf_session.file_collect                    │
│   各フォルダから CSV を収集して確認実行用フォルダに集約          │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 4: 20_jis_to_utf.bat                                │
│   *_jis/ フォルダの CSV を UTF-8 BOM に変換                  │
└──────────────────────────────────────────────────────────┘
```

## スクリプト一覧

ルート直下の `*.bat` がランチャー、`sf_session/` 以下が Python モジュール。

| スクリプト | 役割 |
|---|---|
| `99_setup_初回または設定更新の場合のみ実行する.bat` | venv 作成 + pip upgrade + 依存パッケージ install（初回のみ実行） |
| `sf_session/session_keeper.py` | Chrome 起動 → 手動ログイン待機（SSO / MFA）→ 定期 reload でセッション維持 |
| `sf_session/download.py` | 営業日ガード + pre-flight login check 付きバッチ export orchestration |
| `sf_session/sf_browser_session.py` | Chrome + Selenium session の prepare / close 共通層 (session_keeper / download 共用) |
| `sf_session/download_runner.py` | レポート export 実行エンジン (`export_one` / `export_batch`) |
| `sf_session/download_outputs.py` | ファイル移動先パス組み立て、summary ログ、work_dir swap、完了マーカー |
| `sf_session/business_day.py` | 営業日判定 (土日 + `jpholiday` 祝日) |
| `sf_session/browser.py` | Chrome 起動・WebDriver 接続の共通モジュール |
| `sf_session/login_helper.py` | ログイン/SSO ページ検出・手動ログイン待機・MFA 完了待ち |
| `sf_session/file_deliver.py` | `reportID_*` ファイルをマクロ定義の移動先フォルダへコピー・リネーム + 完了マーカー出力 |
| `sf_session/file_collect.py` | 各フォルダから CSV を収集して `CSV_STAGING_DIR` に集約 (file_deliver の逆) |
| `sf_session/jis_to_utf8.py` | `CSV_STAGING_DIR` 内の CSV を UTF-8 BOM に変換 → `*_utf/` |
| `sf_session/macro_book_reader.py` | ジョブ定義 (`JobEntry`) の読み取り。xlsm から直接読み取り |
| `sf_session/config.py` | 共通パス定数 + `read_ids_file()` + `create_sf_client()` |
| `sf_session/clean.py` | `__pycache__` / `.pyc` / `.log` 等のクリーンアップ |
| `sf_session/report_filter/` | レポートのメタデータ抽出 (API 経由、データ本体は取らない) |

## セットアップ

```powershell
# 初回のみ実行（venv 作成 + 依存 install）
99_setup_初回または設定更新の場合のみ実行する.bat
```

依存: `selenium`, `openpyxl`, `simple-salesforce`, `python-dotenv`, `jpholiday`

## 使い方

bat ファイルをダブルクリック、または PowerShell からオプション付きで実行。
初回は `99_setup_初回または設定更新の場合のみ実行する.bat` を先に実行すること。

### 起動パターン

2 通りの使い方がある。

**パターン A: session_keeper + download（推奨）**

```
■00_keep_session.bat     ← Chrome 起動 + 手動ログイン待機 + セッション維持
★01_download.bat    ← ↑ の Chrome に接続して export
```

session_keeper がセッションを維持するので、長時間の連続 export でも切れにくい。

**パターン B: download 単独**

```
★01_download.bat    ← 自前で Chrome を起動 + 手動ログイン待機 + export
```

session_keeper なしでも動く。download が専用プロファイルで Chrome を起動し、
ログインしてから export を開始する。export 完了後に Chrome は自動終了する。

### ログインの仕組み

SSO 経由のログインに対応。ログインが必要な場合はユーザーが手動で完了するまで待機する。

```
  [Chrome 起動] → [SSO / ログインページ検出] → [手動でログイン]
                                                      │
                                                      ▼
                                                ┌──────────┐
                                                │ MFA 入力 │
                                                │  待ち    │◄─── 2秒ごとに poll
                                                └──────────┘
                                                      │
                                         ┌────────────┴────────────┐
                                         ▼                         ▼
                                   MFA 入力完了             timeout (10分)
                                         │                         │
                                         ▼                         ▼
                                    ログイン完了          ensure_logged_in 再呼出
                                         │                         │
                                         ▼                         ▼
                                      処理開始              [手動ログイン待ち]
                                                                   │
                                                                   ▼
                                                             最初に戻る
                                                           (最大 2 回まで)
```

### 1. セッション確立

```powershell
■00_keep_session.bat
# Chrome 起動 → 手動ログイン待機（SSO / MFA）→ 8分ごとに reload
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
★01_download.bat --dry-run

# 実行 (outputs_csv/ に全ファイル集約)
★01_download.bat

# per-job 振り分け先フォルダへ直接コピー
★01_download.bat --direct-deliver

# ids.txt でフィルタ
11_download_ids.bat

# 失敗分リトライ
12_download_retry.bat

# 日付サフィックス付与
★01_download.bat --date-suffix
```

営業日（平日 + 祝日除外）のみ実行。`--force` で営業日チェックを bypass できる。
起動時に pre-flight login check を行い、ログインが必要なら手動ログインを待機する。
export 中にセッションが切れた場合は、タブを traverse してログイン/SSO ページを検出し、
手動ログイン待機 → 1 回だけリトライする（無限ループ防止）。

主なオプション:

```
--force             営業日チェックを skip して強制実行
--my-chrome         OS デフォルト Chrome を使用（login check skip、手動ログイン前提）
--no-login-check    pre-flight login check を skip
--port              リモートデバッグポート (default: 9222)
--direct-deliver    各ジョブの src_folder_name へ直接振り分け (default: outputs_csv/ に集約)
--ids-file          ids.txt の report ID との intersection でフィルタ
--retry             前回の success_ids を読み、失敗分だけ再実行
--date-suffix       ファイル名に _YYYYMMDD を付与
--interval          レポート間 wait 秒 (default: 2.0)
--timeout           per-report タイムアウト秒 (default: 600)
--open-download-dir Download フォルダを Explorer/Finder で開く
--open-output-dir   出力先フォルダを Explorer/Finder で開く
--dry-run           実行せずジョブ一覧を表示
```

### 3. ファイル振り分け (export 後)

```powershell
# dry-run で振り分け先を確認
★02_振り分け.bat --source-dir outputs_csv --dry-run

# 実行
★02_振り分け.bat --source-dir outputs_csv

# 日付サフィックス + ids.txt フィルタ
★02_振り分け.bat --source-dir outputs_csv --date-suffix --ids-file
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

`★01_download.bat` / `★02_振り分け.bat` の両方で使える。

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

## レポート probe (optional)

API 経由でレポートのメタデータ（名前・列数・列名）を取得する。データ本体はダウンロードしない。

```powershell
py -m sf_session.report_filter
```

- 前提: `.env` に SF 認証情報、`レポートID/ids.txt` に対象 ID を記載
- 出力: `outputs_result/probe_result_{ts}.xlsx`（probe_result シート + columns シート）

## テスト

```bash
python -m pytest -v
```

## クリーンアップ

```powershell
98_clean_cache.bat              # __pycache__, .pyc, .log, .bak 等を削除
98_clean_cache.bat --dry-run    # 削除せず対象だけ表示
```
