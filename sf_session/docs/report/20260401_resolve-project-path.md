# Z: ドライブ未接続時の home fallback — resolve_project_path 導入

## 背景

`MACRO_ROOT_PATH` / `OUTPUT_ROOT_PATH` や macro file 内の `src_folder_name` は
`Z:\Users\you\macros` のような network drive (mapped drive) の path になり得る。

Z: が mount されていない環境（Mac dev、ネットワーク切断時）では
`Path("Z:\\Users\\you\\macros")` が即座に失敗する。

## 方針

config.py に `resolve_project_path()` を追加し、
Z: が見つからない場合に `~/` 配下へ fallback する。

```
Z:\Users\you\macros\archive
  ↓ Z: が存在しない場合
~/Users/you/macros/archive
```

各モジュールで `Path(raw_string)` していた箇所を `resolve_project_path(raw_string)` に置き換える。

## 判定ロジック

起動時に `MACRO_ROOT_PATH` の先頭が `Z:` かつ `exists() == False` なら
`USE_HOME_FALLBACK = True` を立てる。以降すべての path resolve で fallback が適用される。

```
MACRO_ROOT_PATH=Z:\Users\you\macros
                ↓
_expand_path()  → Path("Z:\\Users\\you\\macros")
                ↓
_needs_home_fallback()  → Z: prefix? + not exists()?
                ↓
USE_HOME_FALLBACK = True / False  (module-level, 1回だけ判定)
```

### なぜ MACRO_ROOT_PATH を基準にするか

- `MACRO_ROOT_PATH` と `OUTPUT_ROOT_PATH` は同一 network drive 上にある前提
- path ごとに毎回 `exists()` を叩くと network drive が遅い時に全体が遅延する
- 1つの flag で統一した方が consistent で予測可能
- `MACRO_ROOT_PATH` 未設定（test / CI）の場合は `USE_HOME_FALLBACK = False`

## config.py に追加する関数

```python
def _expand_path(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def _needs_home_fallback(path: Path) -> bool:
    s = str(path).replace("/", "\\")
    return s[:2].lower() == "z:" and not path.exists()


def _to_home_fallback(path: Path) -> Path:
    s = str(path).replace("/", "\\")
    return Path.home() / s[3:]


def resolve_project_path(raw: str | Path) -> Path:
    """外部由来の path を resolve する。Z: が見つからなければ ~/ に fallback。"""
    path = _expand_path(str(raw))
    s = str(path).replace("/", "\\")
    if USE_HOME_FALLBACK and s[:2].lower() == "z:":
        return _to_home_fallback(path)
    return path
```

`USE_HOME_FALLBACK` の判定:

```python
_MACRO_ROOT_RAW = os.environ.get("MACRO_ROOT_PATH")

if _MACRO_ROOT_RAW is None:
    USE_HOME_FALLBACK = False
else:
    USE_HOME_FALLBACK = _needs_home_fallback(_expand_path(_MACRO_ROOT_RAW))
```

config.py 内の path 定数も自身の `resolve_project_path` 経由にする:

```python
_MACRO_ROOT_PATH: Path | None = (
    resolve_project_path(_MACRO_ROOT_RAW) if _MACRO_ROOT_RAW else None
)

OUTPUT_ROOT: Path | None = (
    resolve_project_path(_OUTPUT_ROOT_RAW) if _OUTPUT_ROOT_RAW else None
)
```

## 変更が必要なファイル

### config.py — env var からの Path 構築

```python
# before
_MACRO_ROOT_PATH = Path(os.environ["MACRO_ROOT_PATH"])
OUTPUT_ROOT = Path(os.environ["OUTPUT_ROOT_PATH"])

# after (resolve_project_path 経由)
_MACRO_ROOT_PATH = resolve_project_path(os.environ["MACRO_ROOT_PATH"])
OUTPUT_ROOT = resolve_project_path(os.environ["OUTPUT_ROOT_PATH"])
```

### download/outputs.py — macro file 由来の src_folder_name

`build_destination()` と `probe_destinations()` が `Path(job.src_folder_name)` している。

```python
# build_destination (L43)
# before
dest_dir = output_dir if output_dir else Path(job.src_folder_name)
# after
dest_dir = output_dir if output_dir else resolve_project_path(job.src_folder_name)

# probe_destinations (L117)
# before
probe_output_dir(Path(folder), mkdir=mkdir)
# after
probe_output_dir(resolve_project_path(folder), mkdir=mkdir)
```

### file_collect.py — 収集元フォルダの Path 構築

`_collect_one_job()` と `_dry_run_preview()` が `Path(job.src_folder_name)` している。

```python
# _collect_one_job (L152)
# before
source_folder = Path(job.src_folder_name)
# after
source_folder = resolve_project_path(job.src_folder_name)

# _dry_run_preview (L223)
# before
source_folder = Path(job.src_folder_name)
# after
source_folder = resolve_project_path(job.src_folder_name)
```

### init_pipeline.py — .env を直接 parse して Path を作る箇所

`_get_output_root()` と `_get_macro_root()` が `Path(raw)` している。

```python
# _get_output_root (L155)
# before
return Path(raw)
# after
return resolve_project_path(raw)

# _get_macro_root (L163)
# before
return Path(raw)
# after
return resolve_project_path(raw)
```

## 変更不要なファイル

| ファイル | 理由 |
|---|---|
| file_deliver.py | `build_destination()` を呼ぶだけ。outputs.py 側の修正で OK |
| download/runner.py | resolve 済みの Path を受け取るだけ |
| CHROME_EXE_PATH 等 | ローカルマシンの path。network drive ではない |

## まとめ

| 変更ファイル | 変更箇所 | 内容 |
|---|---|---|
| config.py | 関数追加 + 定数修正 | `resolve_project_path` と helper 3 関数を追加。`_MACRO_ROOT_PATH` / `OUTPUT_ROOT` を経由させる |
| download/outputs.py | L43, L117 | `Path()` → `resolve_project_path()` |
| file_collect.py | L152, L223 | `Path()` → `resolve_project_path()` |
| init_pipeline.py | L155, L163 | `Path()` → `resolve_project_path()` |
