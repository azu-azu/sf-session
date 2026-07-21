"""New pipeline scaffolding tool.

Usage:
    python -m sf_session.init_pipeline              # interactive: create a new pipeline
    python -m sf_session.init_pipeline --ensure     # auto-create missing pipelines from .env
    python -m sf_session.init_pipeline --regen-bats # regenerate bat files of existing pipelines
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from .business_day import EXTRA_HOLIDAYS_PATH
from .config import PIPELINES_DIR, MACRO_ROOT, OUTPUT_ROOT
from .utils import setup_logging

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_DIR.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
_TEMPLATES_DIR = _PACKAGE_DIR / "templates" / "pipeline"
_SUBDIRS = ("result", "ids_file")

_EXTRA_HOLIDAYS_TEMPLATE = """\
# Format: YYYY-MM-DD 
# e.g.:
# 2026-01-01
"""

_BAT_TEMPLATE = """\
@echo off
chcp 65001 >nul
cd /d "%~dp0..\\.."

if not exist ".venv\\Scripts\\python.exe" (
    echo [ERROR] Run setup.bat first.
    if not defined SF_NO_PAUSE pause
    exit /b 1
)

.venv\\Scripts\\python.exe -m {module} {pipeline}{extra_args} %*
rem タスクスケジューラなど無人実行時は SF_NO_PAUSE=1 を設定して pause を抑止する。
rem pause が残るとキー入力待ちで cmd.exe が終了せず、次回トリガが無視される。
if not defined SF_NO_PAUSE pause
"""

_BAT_DEFS = (
    ("01_download.bat",        "sf_session.download",          ""),
    ("02_file_deliver.bat",    "sf_session.file_deliver",      ""),
    ("03_download_direct.bat", "sf_session.download",          " --direct-deliver"),
    ("11_download_ids.bat",    "sf_session.download",          " --ids-file"),
    ("12_download_retry.bat",  "sf_session.download",          " --retry"),
    ("20_jis_to_utf.bat",      "sf_session.jis_to_utf8",       ""),
    ("21_file_collect.bat",    "sf_session.file_collect",      ""),
    ("90_show_macrofile.bat",  "sf_session.macro_book_reader", ""),
)

__devtest_BAT_DEFS = (
    ("00_cleanup_test_csv.bat", "sf_session.cleanup_test_csv", ""),
    ("03_download_direct.bat", "sf_session.download",          " --direct-deliver --mkdir"),
    ("11_download_ids_direct.bat","sf_session.download",       " --ids-file --direct-deliver --mkdir"),
)


# ── helpers ──────────────────────────────────────────────────────────


def _read_env_value(key: str) -> str | None:
    """Read a single value from .env file."""
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
    pattern = re.compile(r"^(PIPELINES\s*=\s*)(.*?)(\s*(?:#.*)?)$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise RuntimeError("PIPELINES line not found in .env")

    current = match.group(2).strip()
    updated = new_name if not current else f"{current}, {new_name}"
    new_text = pattern.sub(rf"\g<1>{updated}\3", text)
    _ENV_PATH.write_text(new_text, encoding="utf-8")
    return updated


_IDS_TXT_TEMPLATE = """\
# 対象の report ID を1行1つ記入する（# 行はコメント）
# 例:
# 00O000000000001AAA
# 00O000000000002AAA
"""


def _create_directories(name: str) -> Path:
    pipeline_dir = PIPELINES_DIR / name
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    for sub in _SUBDIRS:
        (pipeline_dir / sub).mkdir(exist_ok=True)
    ids_txt = pipeline_dir / "ids_file" / "ids.txt"
    if not ids_txt.exists():
        ids_txt.write_text(_IDS_TXT_TEMPLATE, encoding="utf-8")
    return pipeline_dir


def _generate_bat_files(name: str, pipeline_dir: Path) -> int:
    defs = _BAT_DEFS
    if name == "devtest":
        defs = _BAT_DEFS + __devtest_BAT_DEFS
    for filename, module, extra_args in defs:
        content = _BAT_TEMPLATE.format(
            module=module, pipeline=name, extra_args=extra_args,
        )
        (pipeline_dir / filename).write_text(content, encoding="utf-8")
    return len(defs)


def _ensure_macro_dir(name: str, macro_root: Path) -> tuple[Path, bool]:
    macro_dir = macro_root / name
    created = not macro_dir.exists()
    macro_dir.mkdir(parents=True, exist_ok=True)
    return macro_dir, created


def _ensure_output_dir(name: str, output_root: Path) -> tuple[Path, bool]:
    csv_dir = output_root / name / "csv"
    created = not csv_dir.exists()
    csv_dir.mkdir(parents=True, exist_ok=True)
    return csv_dir, created


# ── scaffold ─────────────────────────────────────────────────────────


def _scaffold_pipeline(name: str) -> tuple[Path, int]:
    """Create directories, bat files, and readme for a single pipeline."""
    pipeline_dir = _create_directories(name)
    bat_count = _generate_bat_files(name, pipeline_dir)
    readme_src = _TEMPLATES_DIR / "readme.txt"
    if readme_src.exists():
        (pipeline_dir / "readme.txt").write_text(
            readme_src.read_text(encoding="utf-8"), encoding="utf-8",
        )
    return pipeline_dir, bat_count


# ── main ─────────────────────────────────────────────────────────────


def main() -> None:
    name = input("pipeline名を入力してください: ").strip()

    # validation
    if not name:
        logger.error("pipeline名が空です")
        return
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        logger.error("pipeline名は英数字・ハイフン・アンダースコアのみ使用できます")
        return
    existing = _existing_pipelines()
    if name in existing:
        logger.error("pipeline '%s' は既に存在します: %s", name, ", ".join(existing))
        return

    # 1. update .env
    updated = _update_env_pipelines(name)
    logger.info("\n✓ .env の PIPELINES を更新しました: %s", updated)

    # 2. scaffold (directories + bat files + readme)
    _, bat_count = _scaffold_pipeline(name)
    logger.info("✓ pipelines/%s/ を作成しました", name)
    for sub in _SUBDIRS:
        logger.info("  - %s/", sub)
    logger.info("✓ bat ファイルを配置しました (%d files)", bat_count)
    if (_TEMPLATES_DIR / "readme.txt").exists():
        logger.info("✓ readme.txt を配置しました")

    # 3. macro directory (MACRO_ROOT_PATH)
    if MACRO_ROOT is not None:
        macro_dir, created = _ensure_macro_dir(name, MACRO_ROOT)
        if created:
            logger.info("✓ %s を作成しました", macro_dir)
            logger.info("⚠ マクロファイル（.xlsm） を %s に格納してください", macro_dir)
        else:
            logger.info("✓ %s は既に存在していました", macro_dir)
    else:
        logger.info("⚠ MACRO_ROOT_PATH が未設定のためスキップしました")

    # 4. output directory (OUTPUT_ROOT_PATH)
    if OUTPUT_ROOT is not None:
        csv_dir, csv_created = _ensure_output_dir(name, OUTPUT_ROOT)
        if csv_created:
            logger.info("✓ %s を作成しました", csv_dir)
        else:
            logger.info("✓ %s は既に存在していました", csv_dir)
    else:
        logger.info("⚠ OUTPUT_ROOT_PATH が未設定のためスキップしました")
    logger.info("\nセットアップ完了！")


# ── ensure (batch mode) ──────────────────────────────────────────────


def ensure_pipelines() -> None:
    """PIPELINES に列挙された各 pipeline の scaffold・output dir・macro dir を ensure する。"""
    PIPELINES_DIR.mkdir(parents=True, exist_ok=True)

    # extra_holidays.csv - pipeline 共通なので最初に 1 回だけ ensure
    if not EXTRA_HOLIDAYS_PATH.exists():
        EXTRA_HOLIDAYS_PATH.write_text(_EXTRA_HOLIDAYS_TEMPLATE, encoding="utf-8")
        logger.info("Created %s", EXTRA_HOLIDAYS_PATH)

    names = _existing_pipelines()
    if not names:
        return

    if MACRO_ROOT is None:
        logger.warning("MACRO_ROOT_PATH not found — skipping macro dirs")
    if OUTPUT_ROOT is None:
        logger.warning("OUTPUT_ROOT_PATH not found — skipping output dirs")

    for name in names:
        # scaffold only if pipelines/ dir doesn't exist yet
        pipeline_dir = PIPELINES_DIR / name

        if not pipeline_dir.exists():
            logger.info("Creating missing pipeline: %s", name)
            _scaffold_pipeline(name)
            logger.info("Created pipeline: %s", name)

        # macro directory — always ensure (failure is non-fatal)
        if MACRO_ROOT is not None:
            macro_dir, created = _ensure_macro_dir(name, MACRO_ROOT)
            if created:
                logger.info("Created macro dir: %s", macro_dir)

        # output directory — always ensure (failure is non-fatal)
        if OUTPUT_ROOT is not None:
            csv_dir, created = _ensure_output_dir(name, OUTPUT_ROOT)
            if created:
                logger.info("Created output dir: %s", csv_dir)


# ── regen bats (existing pipelines) ──────────────────────────────────


def regenerate_bats() -> None:
    """既存 pipeline の bat ファイルを現在のテンプレートで上書き再生成する。

    ディレクトリ構成・ids.txt・readme などは触らず、bat だけを更新する。
    テンプレート更新（例: SF_NO_PAUSE ガード追加）を、既に scaffold 済みの
    pipeline に反映させたいときに使う。
    """
    names = _existing_pipelines()
    if not names:
        logger.info("PIPELINES が空のため再生成対象がありません")
        return

    for name in names:
        pipeline_dir = PIPELINES_DIR / name
        if not pipeline_dir.is_dir():
            logger.warning(
                "pipelines/%s が存在しないため skip（先に --ensure が必要）", name,
            )
            continue
        count = _generate_bat_files(name, pipeline_dir)
        logger.info("bat を再生成しました: pipelines/%s (%d files)", name, count)


if __name__ == "__main__":
    setup_logging()

    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--ensure":
        ensure_pipelines()
    elif arg == "--regen-bats":
        regenerate_bats()
    else:
        main()
