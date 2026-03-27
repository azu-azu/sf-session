"""New pipeline scaffolding tool.

Usage:
    python -m sf_session.init_pipeline
"""

from __future__ import annotations

import re
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_DIR.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
_PIPELINES_DIR = _PROJECT_ROOT / "pipelines"
_TEMPLATES_DIR = _PACKAGE_DIR / "templates" / "pipeline"
_SUBDIRS = ("result", "ids_file")

_BAT_TEMPLATE = """\
@echo off
cd /d "%~dp0..\\.."

if not exist ".venv\\Scripts\\python.exe" (
    echo [ERROR] Run setup.bat first.
    pause
    exit /b 1
)

.venv\\Scripts\\python.exe -m {module} {pipeline}{extra_args} %*
pause
"""

_BAT_DEFS = (
    ("★01_download.bat",      "sf_session.download",          ""),
    ("★02_振り分け.bat",       "sf_session.file_deliver",      ""),
    ("03_download_direct.bat", "sf_session.download",          " --direct-deliver"),
    ("11_download_ids.bat",    "sf_session.download",          " --ids-file"),
    ("12_download_retry.bat",  "sf_session.download",          " --retry"),
    ("20_jis_to_utf.bat",      "sf_session.jis_to_utf8",       ""),
    ("21_file_collect.bat",    "sf_session.file_collect",       ""),
    ("90_show_macrofile.bat",  "sf_session.macro_book_reader",  ""),
)


# ── helpers ──────────────────────────────────────────────────────────


def _read_env_value(key: str) -> str | None:
    """Read a single value from .env without importing config."""
    if not _ENV_PATH.exists():
        return None
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith(f"{key}="):
            return stripped.split("=", 1)[1].strip()
    return None


def _existing_pipelines() -> list[str]:
    raw = _read_env_value("PIPELINES") or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def _update_env_pipelines(new_name: str) -> str:
    """Append *new_name* to the PIPELINES line in .env and return the updated value."""
    text = _ENV_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r"^(PIPELINES\s*=\s*)(.+?)(\s*(?:#.*)?)$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise RuntimeError("PIPELINES line not found in .env")

    current = match.group(2).strip()
    updated = f"{current}, {new_name}"
    new_text = pattern.sub(rf"\g<1>{updated}\3", text)
    _ENV_PATH.write_text(new_text, encoding="utf-8")
    return updated


def _create_directories(name: str) -> Path:
    pipeline_dir = _PIPELINES_DIR / name
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    for sub in _SUBDIRS:
        (pipeline_dir / sub).mkdir(exist_ok=True)
    return pipeline_dir


def _generate_bat_files(name: str, pipeline_dir: Path) -> int:
    for filename, module, extra_args in _BAT_DEFS:
        content = _BAT_TEMPLATE.format(
            module=module, pipeline=name, extra_args=extra_args,
        )
        (pipeline_dir / filename).write_text(content, encoding="utf-8")
    return len(_BAT_DEFS)


def _get_output_root() -> Path:
    """OUTPUT_ROOT_PATH を .env から取得する。"""
    raw = _read_env_value("OUTPUT_ROOT_PATH")
    if not raw:
        raise RuntimeError("OUTPUT_ROOT_PATH not found in .env")
    return Path(raw)


def _ensure_macro_dir(name: str) -> tuple[Path, bool]:
    macro_root_raw = _read_env_value("MACRO_ROOT_PATH")
    if not macro_root_raw:
        raise RuntimeError("MACRO_ROOT_PATH not found in .env")
    macro_dir = Path(macro_root_raw) / name
    created = not macro_dir.exists()
    macro_dir.mkdir(parents=True, exist_ok=True)
    return macro_dir, created


def _ensure_output_dir(name: str, output_root: Path) -> tuple[Path, bool]:
    csv_dir = output_root / name / "csv"
    created = not csv_dir.exists()
    csv_dir.mkdir(parents=True, exist_ok=True)
    return csv_dir, created


# ── main ─────────────────────────────────────────────────────────────


def main() -> None:
    name = input("pipeline名を入力してください: ").strip()

    # validation
    if not name:
        print("[ERROR] pipeline名が空です")
        return
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        print("[ERROR] pipeline名は英数字・ハイフン・アンダースコアのみ使用できます")
        return
    existing = _existing_pipelines()
    if name in existing:
        print(f"[ERROR] pipeline '{name}' は既に存在します: {', '.join(existing)}")
        return

    # 1. update .env
    updated = _update_env_pipelines(name)
    print(f"\n✓ .env の PIPELINES を更新しました: {updated}")

    # 2. create directories
    pipeline_dir = _create_directories(name)
    print(f"✓ pipelines/{name}/ を作成しました")
    for sub in _SUBDIRS:
        print(f"  - {sub}/")

    # 3. generate bat files
    count = _generate_bat_files(name, pipeline_dir)
    print(f"✓ bat ファイルを配置しました ({count} files)")

    # 4. copy readme.txt
    readme_src = _TEMPLATES_DIR / "readme.txt"
    if readme_src.exists():
        (pipeline_dir / "readme.txt").write_text(
            readme_src.read_text(encoding="utf-8"), encoding="utf-8"
        )
        print("✓ readme.txt を配置しました")

    # 5. macro directory (MACRO_ROOT_PATH)
    try:
        macro_dir, created = _ensure_macro_dir(name)
        if created:
            print(f"✓ {macro_dir} を作成しました")
            print(f"⚠ マクロファイル (.xlsm) を {macro_dir} に格納してください")
        else:
            print(f"✓ {macro_dir} は既に存在します")
    except RuntimeError as e:
        print(f"⚠ MACRO_ROOT_PATH の処理をスキップしました: {e}")

    # 6. output directory (OUTPUT_ROOT_PATH)
    try:
        output_root = _get_output_root()
        csv_dir, csv_created = _ensure_output_dir(name, output_root)
        if csv_created:
            print(f"✓ {csv_dir} を作成しました")
        else:
            print(f"✓ {csv_dir} は既に存在します")
    except RuntimeError as e:
        print(f"⚠ OUTPUT_ROOT_PATH の処理をスキップしました: {e}")

    print("\nセットアップ完了！")


if __name__ == "__main__":
    main()
