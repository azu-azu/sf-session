"""devtest 用 CSV クリーンアップスクリプト。

download / direct-deliver で生成されたテスト用 CSV を一括削除する。
csv_dir（+ _prev_* / _work_* ）と、マクロ定義の振り分け先フォルダが対象。

Usage:
    python -m sf_session.cleanup_test_csv devtest
    python -m sf_session.cleanup_test_csv devtest --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import PIPELINES, VALID_PIPELINES
from .macro_book_reader import read_jobs
from .utils import setup_logging

logger = logging.getLogger(__name__)

# devtest 以外で誤実行すると本番 CSV が消えるため safety guard を入れている。
# 別 pipeline で使いたい場合は False に変更する。
# → ただし実行後は必ず True に戻すこと。取扱要注意。
_DEVTEST_ONLY = True


def _collect_csv_dir_targets(csv_dir: Path) -> list[Path]:
    """csv_dir 本体 + _prev_* / _work_* の sibling を収集する。"""
    targets: list[Path] = []
    if csv_dir.is_dir():
        targets.append(csv_dir)
    parent = csv_dir.parent
    for pattern in (f"{csv_dir.name}_prev_*", f"{csv_dir.name}_work_*"):
        targets.extend(sorted(d for d in parent.glob(pattern) if d.is_dir()))
    return targets


def _delete_csv_in_dir(directory: Path, *, dry_run: bool) -> int:
    """directory 内の *.csv を削除し、削除件数を返す。"""
    count = 0
    for f in sorted(directory.glob("*.csv")):
        if not f.is_file():
            continue
        if dry_run:
            logger.info("  [dry-run] delete: %s", f)
        else:
            f.unlink()
            logger.info("  deleted: %s", f)
        count += 1
    return count


def _delete_dir_if_empty(directory: Path, *, dry_run: bool) -> None:
    """_prev_* / _work_* ディレクトリが空なら削除する。"""
    if not directory.is_dir():
        return
    remaining = list(directory.iterdir())
    if not remaining:
        if dry_run:
            logger.info("  [dry-run] rmdir: %s", directory)
        else:
            directory.rmdir()
            logger.info("  rmdir: %s", directory)


def _collect_direct_folders(macro_dir: Path) -> list[str]:
    """マクロ定義から振り分け先フォルダ一覧を取得する。"""
    try:
        jobs = read_jobs(macro_dir)
    except FileNotFoundError as e:
        logger.warning("マクロ読み取りスキップ: %s", e)
        return []

    seen: set[str] = set()
    folders: list[str] = []
    for job in jobs:
        folder = job.src_folder_name
        if folder and folder not in seen:
            seen.add(folder)
            folders.append(folder)
    return folders


def run(pipeline_name: str, *, dry_run: bool = False) -> int:
    """指定 pipeline の CSV を一括削除する。return: 削除した総件数。"""
    if _DEVTEST_ONLY and pipeline_name != "devtest":
        raise SystemExit(f"[ERROR] '{pipeline_name}' は cleanup 対象外です。")
    pipeline = PIPELINES[pipeline_name]
    total = 0

    # 1. csv_dir + _prev_* / _work_*
    csv_dir = pipeline.csv_dir
    targets = _collect_csv_dir_targets(csv_dir)
    if targets:
        logger.info("--- csv_dir 系 ---")
        for d in targets:
            logger.info("[%s]", d)
            total += _delete_csv_in_dir(d, dry_run=dry_run)
            if d != csv_dir:
                _delete_dir_if_empty(d, dry_run=dry_run)
    else:
        logger.info("csv_dir が存在しません: %s", csv_dir)

    # 2. direct-deliver 先 (マクロ定義の src_folder_name)
    folders = _collect_direct_folders(pipeline.macro_dir)
    if folders:
        logger.info("--- direct-deliver 先 ---")
        for folder in folders:
            p = Path(folder)
            if not p.is_dir():
                logger.info("[%s] (存在しない — skip)", p)
                continue
            logger.info("[%s]", p)
            total += _delete_csv_in_dir(p, dry_run=dry_run)

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
