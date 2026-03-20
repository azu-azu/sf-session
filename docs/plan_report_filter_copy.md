# Plan: sf-other の filter-extract 機能を sf-session にコピー

## Context

sf-other の `filter-extract` コマンドは Salesforce レポートの metadata（行数、列数、フィルタ条件、オブジェクト情報）を API 経由で取得する。データ本体は取らない。

sf-session からもこの機能を使いたいが、sf-other を subprocess で呼ぶのではなく、必要なコードを sf-session 内にコピーして独立させる。

## 方針

sf-other の `generators/report_filter_*` 系モジュール群を `sf_session/report_filter/` パッケージとしてコピー。sf-session の既存インフラ（`create_sf_client`, `read_ids_file`）を再利用し、sf-other 固有の依存は除去。

## コピー対象（sf-other → sf-session）

### 新規パッケージ: `sf_session/report_filter/`

| sf-other 元ファイル | sf-session 先 | 変更点 |
|---|---|---|
| `generators/report_filter_job.py` | `report_filter/job.py` | import を sf_session 用に書き換え、`cli_utils.format_elapsed` をインライン化 |
| `generators/report_filter_metadata.py` | `report_filter/metadata.py` | import 書き換えのみ |
| `generators/report_filter_extractor.py` | `report_filter/extractor.py` | import 書き換えのみ |
| `generators/report_filter_annotator.py` | `report_filter/annotator.py` | import 書き換えのみ |
| `generators/report_filter_operators.py` | `report_filter/operators.py` | config 定数をモジュール内にインライン化 |
| `generators/report_filter_writer.py` | `report_filter/writer.py` | import 書き換え、`deduplicate_ids` をインライン化 |
| `generators/_shared.py` | `report_filter/_shared.py` | そのままコピー |
| `connectors/support/analytics_reports_api.py` | `report_filter/analytics_api.py` | そのままコピー |

### 新規ファイル: `sf_session/report_filter/__init__.py`

public API として `run_report_filter_extract_job` を export。

### 新規ファイル: `sf_session/report_filter/__main__.py`

CLI entry point:
```python
"""python -m sf_session.report_filter で実行。"""
from .job import run_report_filter_extract_job
from ..config import create_sf_client, DEFAULT_IDS_FILE
from ..utils import read_ids_file, setup_logging
```

report ID は sf-session 既存の `read_ids_file(DEFAULT_IDS_FILE)` を使う。
SF client は `create_sf_client()` を使う。

## sf-other 依存の除去

| sf-other の依存 | sf-session での対応 |
|---|---|
| `cli_utils.format_elapsed()` | `job.py` にインライン（3行の関数） |
| `cli_utils.deduplicate_ids()` | `writer.py` にインライン（3行の関数） |
| `config.DEFAULT_PIPELINE_DIR` | `sf_session/config.py` に `PIPELINE_DIR = PROJECT_ROOT / "pipelines"` を追加 |
| `config.OUTPUT_ERRORS_DIR` | `sf_session/config.py` に `OUTPUT_ERRORS_DIR = PROJECT_ROOT / "outputs_log" / "errors"` を追加 |
| `config.SF_NOTCONTAIN_*`, `_TRUTHY` | `operators.py` 内にインライン |
| `exceptions.py` | 不要（使用箇所なし） |
| `shared.ids` | sf-session の `utils.read_ids_file` を使用 |
| `popup.show_popup` | 不要（CLI通知は logger で十分） |

## 出力先

sf-other と同じ構造:
```
outputs_log/report_filters/
  ├── report_filters.json
  ├── report_filters_metadata.json
  ├── report_filters_auto.json
  ├── report_filters_manual.json
  ├── report_ids_auto.txt
  └── report_ids_manual.txt
outputs_log/errors/
  └── report_setup_errors.log
pipelines/{report_id}/
  └── report_metadata.json
```

## 外部パッケージ

`simple-salesforce` — sf-session の requirements.txt に既に存在。追加不要。

## Critical Files

| File | Action |
|------|--------|
| `sf_session/report_filter/__init__.py` | 新規 |
| `sf_session/report_filter/__main__.py` | 新規（CLI entry） |
| `sf_session/report_filter/job.py` | コピー + import 書き換え |
| `sf_session/report_filter/metadata.py` | コピー + import 書き換え |
| `sf_session/report_filter/extractor.py` | コピー + import 書き換え |
| `sf_session/report_filter/annotator.py` | コピー + import 書き換え |
| `sf_session/report_filter/operators.py` | コピー + 定数インライン化 |
| `sf_session/report_filter/writer.py` | コピー + import 書き換え |
| `sf_session/report_filter/_shared.py` | コピー |
| `sf_session/report_filter/analytics_api.py` | コピー |

## 設計判断メモ

### パスは PROJECT_ROOT 基準にする（cwd 依存を避ける）

`pipelines/` や `outputs_log/` を `Path("pipelines")` のように相対パスで書くと、
実行時の cwd によって出力先が変わる。`config.py` の `PROJECT_ROOT` から解決することで、
`python -m sf_session.report_filter` をどこから実行しても同じ場所に出力される。

### analytics_api.py は将来 shared 化の候補

sf-other の `connectors/support/analytics_reports_api.py` をそのままコピーする。
短期的にはこれで正しいが、sf-other 側が API 呼び出しを改善した場合、
sf-session 側が古いまま取り残されるリスクがある。
将来的には shared パッケージとして切り出すか、sf-other を pip install して import する形を検討。

### report_filter は optional utility として扱う

sf-session の主機能（session 維持・DL・振り分け）とは責務が異なる。
`sf_session/report_filter/` に閉じ込めて、既存コードとの混在を避ける。
README でも「optional utility」寄りの扱いにする。

## Verification

1. `python3 -m pytest -v` → 既存テスト全 pass（regression なし）
2. `python3 -c "from sf_session.report_filter import run_report_filter_extract_job"` → import 成功
3. .env に SF 認証情報がある環境で `python3 -m sf_session.report_filter` → metadata 取得・JSON 出力
