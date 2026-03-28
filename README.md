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
| `01_stay_awake.bat` | Windows スリープ防止（`--minutes` で時間指定、0 で無制限） |
| `98_setup_初回または設定更新の場合のみ実行する.bat` | venv 作成 + pip upgrade + 依存パッケージ install + missing pipeline 自動作成（初回のみ実行） |
| `sf_session/keeper.py` | Chrome 起動 → 手動ログイン待機（SSO / MFA）→ 定期 reload でセッション維持 |
| `sf_session/download/cli.py` | 営業日ガード + pre-flight login check 付きバッチ export orchestration |
| `sf_session/download/runner.py` | レポート export 実行エンジン (export_one / export_batch) |
| `sf_session/download/outputs.py` | ファイル移動先パス組み立て、summary ログ、work_dir swap、完了マーカー、移動先 probe |
| `sf_session/download/single.py` | Chrome CLI 実行 + ダウンロード監視 |
| `sf_session/session.py` | Chrome + Selenium session の prepare / close 共通層 (keeper / download 共用) |
| `sf_session/business_day.py` | 営業日判定 (土日 + `jpholiday` 祝日 + `extra_holidays.csv`) |
| `sf_session/stay_awake.py` | Windows スリープ防止 (`SetThreadExecutionState` API) |
| `sf_session/browser.py` | Chrome 起動・WebDriver 接続の共通モジュール |
| `sf_session/login_helper.py` | ログイン/SSO ページ検出・手動ログイン待機・MFA 完了待ち |
| `sf_session/file_deliver.py` | `reportID_*` ファイルをマクロ定義の移動先フォルダへコピー・リネーム + 移動先 probe + 完了マーカー出力 |
| `sf_session/file_collect.py` | 各フォルダから CSV を収集して `ARCHIVE_CSV_DIR` に集約 (file_deliver の逆) |
| `sf_session/jis_to_utf8.py` | `ARCHIVE_CSV_DIR` 内の CSV を UTF-8 BOM に変換 → `*_utf/` |
| `sf_session/macro_book_reader.py` | ジョブ定義 (`JobEntry`) の読み取り。xlsm から直接読み取り |
| `sf_session/config.py` | 共通パス定数 + `create_sf_client()` |
| `sf_session/clean.py` | `__pycache__` / `.pyc` / `.log` 等のクリーンアップ |
| `sf_session/cleanup_test_csv.py` | テスト用 CSV の一括削除 (devtest 専用、safety guard 付き) |
| `sf_session/init_pipeline.py` | 新規 pipeline の scaffolding（ディレクトリ・bat・.env を一括生成）。`--ensure` で .env 記載の missing pipeline を自動作成 |
| `sf_session/report_filter/` | レポートのメタデータ抽出 (API 経由、データ本体は取らない) |

## セットアップ

```powershell
# 初回のみ実行（venv 作成 + 依存 install + missing pipeline 自動作成）
98_setup_初回または設定更新の場合のみ実行する.bat
```

依存: `selenium`, `openpyxl`, `simple-salesforce`, `python-dotenv`, `jpholiday`

## 使い方

bat ファイルをダブルクリック、または PowerShell からオプション付きで実行。
初回は `98_setup_初回または設定更新の場合のみ実行する.bat` を先に実行すること。

### 起動パターン

2 通りの使い方がある。

**パターン A: keeper + download（推奨）**

```
■00_keep_session.bat     ← Chrome 起動 + 手動ログイン待機 + セッション維持
★01_download.bat    ← ↑ の Chrome に接続して export
```

keeper がセッションを維持するので、長時間の連続 export でも切れにくい。

**パターン B: download 単独**

```
★01_download.bat    ← 自前で Chrome を起動 + 手動ログイン待機 + export
```

keeper なしでも動く。download が専用プロファイルで Chrome を起動し、
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

# 実行 (OUTPUT_ROOT_PATH/archive/csv/ に全ファイル集約)
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

営業日（平日 + 祝日 + `extra_holidays.csv` 除外）のみ実行。`--force` で営業日チェックを bypass できる。
起動時に pre-flight login check を行い、ログインが必要なら手動ログインを待機する。
`--direct-deliver` 時は export 前に全移動先フォルダの到達性を probe し、
1 つでもアクセス不可なら即座に abort する（network folder 切断時の数分ロスを防止）。
export 中にセッションが切れた場合は、タブを traverse してログイン/SSO ページを検出し、
手動ログイン待機 → 1 回だけリトライする（無限ループ防止）。

主な failure パターンと retry:

| 原因 | 頻度 | 詳細 |
|---|---|---|
| Timeout (600s) | 最多 | レポートが巨大 or SF 側が高負荷で DL 完了しない |
| セッション切れ | たまに | SSO セッション期限切れ → login recovery (1回) も失敗した場合 |
| Chrome 起動失敗 | 稀 | ポート競合や Chrome が既に占有 |
| ファイル移動失敗 | 稀 | network folder (Box) 切断で `shutil.move` が失敗 |

いずれも一時的な問題なので、時間をおいて `12_download_retry.bat` で通ることが多い。
`--direct-deliver` で実行した後でも `success_ids` は記録されるため、retry bat はそのまま使える（出力先は `csv/` になるので `★02_振り分け.bat` で振り分ける）。

主なオプション:

```
--force             営業日チェックを skip して強制実行
--my-chrome         OS デフォルト Chrome を使用（login check skip、手動ログイン前提）
--no-login-check    pre-flight login check を skip
--port              リモートデバッグポート (default: 9222)
--direct-deliver    各ジョブの src_folder_name へ直接振り分け (default: OUTPUT_ROOT_PATH/archive/csv/ に集約)
--ids-file          ids.txt の report ID との intersection でフィルタ
--retry             前回の success_ids を読み、失敗分だけ再実行
--date-suffix       ファイル名に _YYYYMMDD を付与
--interval          レポート間 wait 秒 (default: 2.0)
--timeout           per-report タイムアウト秒 (default: 600)
--mkdir             移動先フォルダが存在しない場合、親があれば最終フォルダを自動作成
--open-download-dir Download フォルダを Explorer で開く
--open-output-dir   出力先フォルダを Explorer で開く
--dry-run           実行せずジョブ一覧を表示
```

### 3. ファイル振り分け (export 後)

```powershell
# dry-run で振り分け先を確認
★02_振り分け.bat --dry-run

# 実行 (source-dir 省略時は pipeline の csv/ を参照)
★02_振り分け.bat

# 別フォルダを指定する場合
★02_振り分け.bat --source-dir /other/path

# ids.txt でフィルタ
★02_振り分け.bat --ids-file
```

実行前に全振り分け先フォルダの到達性を probe し、1 つでもアクセス不可なら即座に abort する。
`--mkdir` を付けると、親フォルダが存在する場合に最終フォルダを自動作成する。
`--dry-run` 時は probe をスキップする。

## extra_holidays.csv — 追加休業日

`pipelines/extra_holidays.csv` に日付を書くと、営業日チェックで非営業日として扱う。
年末年始や会社独自の休業日など、祝日以外の非稼働日を追加する用途。

- **置き場所**: `pipelines/extra_holidays.csv`
- **フォーマット**: 1 行 1 日付 (`YYYY-MM-DD`)
- 空行・parse できない行はスキップ（warning ログ出力）
- ファイルが存在しなければ無視（既存動作に影響なし）

```text
2026-12-31
2027-01-02
2027-01-03
```

## ids.txt — レポート ID フィルタ

`--ids-file` フラグを付けると、`ids.txt` に書かれた report ID だけを処理対象にする。

- **置き場所**: `pipelines/<pipeline>/ids_file/ids.txt`
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

`MACRO_ROOT_PATH/<pipeline>/` に配置した `.xlsm` の `Salesforce` シートから直接読み取る。

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

- 前提: `.env` に SF 認証情報
- 対象: マクロ定義 (`.xlsm`) の全レポート ID を自動取得
- 出力: `pipelines/archive/result/probe_result_{ts}.xlsx`（probe_result シート + columns シート）

## マーカーファイル

各ステップの実行状態を示す txt ファイルが自動生成される。

| マーカー | 配置先 | 用途 |
|---|---|---|
| `★{time}_START_{N}件の予定.txt` | csv_dir (`OUTPUT_ROOT/{pipeline}/csv/`) | download 開始マーカー |
| `★{time}_成功{N}件_失敗{N}件.txt` | csv_dir (`OUTPUT_ROOT/{pipeline}/csv/`) | download 完了マーカー |
| `★{time}_振り分け完了.txt` | source_dir (= csv_dir) | file_deliver 完了マーカー |
| `_{pipeline}_{phase}_{label}.txt` | `OUTPUT_ROOT.parent` | pipeline status マーカー |

```
OUTPUT_ROOT.parent/
  _archive_dl_3月28日09時30分_成功2件_失敗0件.txt      ← download 通常モード
  _archive_direct_3月28日09時30分_成功2件_失敗0件.txt  ← download --direct-deliver
  _archive_dv_3月28日09時30分_振り分け完了.txt          ← file_deliver
  OUTPUT_ROOT/
    archive/
      csv/
        ★3月28日09時30分_START_2件の予定.txt
        ★3月28日09時30分_成功2件_失敗0件.txt
        ★3月28日09時30分_振り分け完了.txt
        00O000001_20260328_report_001.csv
        00O000002_20260328_report_002.csv
```

## テスト

```powershell
py -m pytest -v
```

## クリーンアップ

```powershell
97_clean_cache.bat              # __pycache__, .pyc, .log, .bak 等を削除
97_clean_cache.bat --dry-run    # 削除せず対象だけ表示
```

### テスト用 CSV の削除 (devtest 専用)

```powershell
■00_cleanup_test_csv.bat             # csv_dir + direct-deliver 先の *.csv を一括削除
■00_cleanup_test_csv.bat --dry-run   # 削除せず対象だけ表示
```

devtest pipeline の csv_dir（`_prev_*` / `_work_*` 含む）と、マクロ定義の振り分け先フォルダから `*.csv` を削除する。
本番 pipeline での誤実行を防ぐため、devtest 以外では safety guard で拒否される。

## 新規 pipeline の追加

```powershell
99_new_pipeline.bat
```

対話形式で pipeline 名を入力すると、ディレクトリ・bat・readme・.env を一括生成する。
csv 出力先は `OUTPUT_ROOT_PATH/<pipeline>/csv/` に作成される（`.env` で設定）。
