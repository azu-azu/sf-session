"""_devtest 用 CSV クリーンアップスクリプト。

- pipeline.csv_dir 配下の csv を再帰削除
- マクロファイル定義の振り分け先フォルダがあれば、そこも再帰削除

Usage:
    python -m sf_session.cleanup_test_csv _devtest
    python -m sf_session.cleanup_test_csv _devtest --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import PIPELINES, VALID_PIPELINES, resolve_project_path
from .macro_book_reader import read_jobs
from .utils import setup_logging

logger = logging.getLogger(__name__)

# _devtest 以外で誤実行すると本番 CSV が消えるため safety guard を入れている。
# 別 pipeline で使いたい場合は False に変更する。
# → ただし実行後は必ず True に戻すこと。取扱要注意。
__devtest_ONLY = True


def _delete_csv_recursive(directory: Path, *, dry_run: bool) -> int:
    """directory 配下の *.csv を再帰削除して件数を返す。"""
    if not directory.is_dir():
        logger.info("[%s] (NOT exists - skip)", directory)
        return

    count = 0
    logger.info("[%s]", directory)
    for path in sorted(directory.rglob("*.csv")):
        if not path.is_file():
            continue
        if dry_run:
            logger.info("[dry-run] delete: %s", path)
        else:
            path.unlink()
            logger.info("deleted: %s", path)
        count += 1
    return count


def _collect_extra_dirs(macro_dir: Path, base_dir: Path) -> list[Path]:
    """マクロファイル定義の振り分け先フォルダから、base_dir 以外の実在パスを集める。"""
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
    if __devtest_ONLY and pipeline_name != "_devtest":
        raise SystemExit(f"[Error] '{pipeline_name}' は cleanup 対象外です。")

    pipeline = PIPELINES[pipeline_name]
    base_dir = resolve_project_path(pipeline.csv_dir).parent
    total = 0

    logger.info("--- csv_dir ---")
    total += _delete_csv_recursive(base_dir, dry_run=dry_run)

    extra_dirs = _collect_extra_dirs(pipeline.macro_dir, base_dir)
    if extra_dirs:
        logger.info("--- extra destinations ---")
        for directory in extra_dirs:
            total =+ _delete_csv_recursive(directory, dry_run=dry_run)

    label = "dry-run" if dry_run else "deleted"
    logger.info("合計 %d 件 %s", total, label)
    return total


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="テスト用 CSV を一括削除する (_devtest 向け)",
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