"""devtest 用 CSV クリーンアップスクリプト。

- pipeline 出力ルート（csv_dir の親）配下の CSV を再帰削除
- マクロ定義の振り分け先フォルダがあれば、そこも再帰削除

Usage:
    python -m sf_session.cleanup_test_csv devtest
    python -m sf_session.cleanup_test_csv devtest --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import PIPELINES, VALID_PIPELINES, resolve_project_path
from .macro_book_reader import read_jobs
from .utils import setup_logging, short_path

logger = logging.getLogger(__name__)

_DEVTEST_ONLY = True


def _delete_csv_recursive(directory: Path, *, dry_run: bool) -> int:
    """directory 配下の *.csv を再帰削除して件数を返す。"""
    if not directory.is_dir():
        logger.info("[%s] (存在しない — skip)", short_path(directory))
        return 0

    count = 0
    logger.info("[%s]", short_path(directory))
    for path in sorted(directory.rglob("*.csv")):
        if not path.is_file():
            continue
        if dry_run:
            logger.info("  [dry-run] delete: %s", short_path(path))
        else:
            path.unlink()
            logger.info("  deleted: %s", short_path(path))
        count += 1
    return count


def _collect_extra_dirs(macro_dir: Path, base_dir: Path) -> list[Path]:
    try:
        jobs = read_jobs(macro_dir)
    except FileNotFoundError as e:
        logger.warning("マクロ読み取りスキップ: %s", e)
        return []

    seen: set[Path] = set()
    extra_dirs: list[Path] = []

    for job in jobs:
        folder = job.src_folder_name
        if not folder:
            continue

        path = resolve_project_path(folder)

        if path == base_dir or base_dir in path.parents:
            continue
        if path in seen:
            continue

        seen.add(path)
        extra_dirs.append(path)

    return extra_dirs


def run(pipeline_name: str, *, dry_run: bool = False) -> int:
    if _DEVTEST_ONLY and pipeline_name != "devtest":
        raise SystemExit(f"[ERROR] '{pipeline_name}' は cleanup 対象外です。")

    pipeline = PIPELINES[pipeline_name]
    base_dir = pipeline.csv_dir.parent
    total = 0

    logger.info("--- csv_dir ---")
    total += _delete_csv_recursive(base_dir, dry_run=dry_run)

    extra_dirs = _collect_extra_dirs(pipeline.macro_dir, base_dir)
    if extra_dirs:
        logger.info("--- extra destinations ---")
        for directory in extra_dirs:
            total += _delete_csv_recursive(directory, dry_run=dry_run)

    label = "dry-run" if dry_run else "deleted"
    logger.info("合計 %d 件 %s", total, label)
    return total


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="テスト用 CSV を一括削除する (devtest 向け)",
    )
    parser.add_argument(
        "pipeline",
        choices=VALID_PIPELINES,
        help="対象の pipeline 名",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="削除せず対象ファイルを一覧表示",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    run(args.pipeline, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
