"""macro_book_reader のジョブ定義と success ID で対象 CSV を特定し、日付フォルダへコピーする。

file_deliver の逆操作: 各フォルダから CSV を収集して CSV_STAGING_DIR に集約する。

Usage:
    python -m sf_session.file_collect
"""

from __future__ import annotations

import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .config import CSV_STAGING_DIR, OUTPUT_RESULTS_DIR
from .macro_book_reader import JobEntry, read_jobs
from .utils import (
    find_latest_success_ids,
    read_ids_file,
    setup_logging,
    strip_trailing_date,
)

logger = logging.getLogger(__name__)

_COLLECT_FOLDER_TEMPLATE = "#_jis"


def _dump_csv_list(csvs: list[Path]) -> None:
    """フォルダ内の CSV ファイルと mtime を出力する（検索失敗時の診断用）。"""
    lines = [
        f"  {p.name}  mtime={datetime.fromtimestamp(p.stat().st_mtime)}"
        for p in csvs[:10]
    ]
    if len(csvs) > 10:
        lines.append(f"  ... 他 {len(csvs) - 10} 件")
    logger.warning("フォルダ内の CSV:\n%s", "\n".join(lines))


def _find_csv_by_name(
    source_folder: Path, name_fragment: str, today_str: str
) -> Path | None:
    """指定されたベース名 + 今日の日付サフィックスの CSV を優先的に返す。

    Network drive では mtime が信用できないため、ファイル名の日付を優先する。
    """
    csvs = list(source_folder.glob("*.csv"))
    today_exact = f"{name_fragment}_{today_str}.csv"

    for p in csvs:
        if p.name == today_exact:
            return p

    # fallback: name_fragment を含む CSV のうち mtime 最新
    matches = [p for p in csvs if name_fragment in p.name]
    if not matches:
        if csvs:
            _dump_csv_list(csvs)
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _find_csv_by_date(source_folder: Path, today_str: str) -> Path | None:
    """今日の日付サフィックス or 今日更新された CSV を検索する。"""
    csvs = list(source_folder.glob("*.csv"))

    for p in csvs:
        if p.name.lower().endswith(f"{today_str}.csv"):
            return p

    latest = None
    latest_mtime = None
    today_date = datetime.strptime(today_str, "%Y%m%d").date()
    for p in csvs:
        mod_time = datetime.fromtimestamp(p.stat().st_mtime)
        if mod_time.date() == today_date:
            if latest is None or mod_time > latest_mtime:
                latest = p
                latest_mtime = mod_time

    if latest is None and csvs:
        _dump_csv_list(csvs)
    return latest


def _collect_one_job(
    job: JobEntry,
    today_str: str,
    daily_output_folder: Path,
) -> bool:
    """1ジョブ分の CSV を検索・コピーする。成功なら True。"""
    source_folder = Path(job.src_folder_name)
    if not source_folder.is_dir():
        logger.warning("フォルダが見つかりません: %s (No: %s)。スキップ。", source_folder, job.no)
        return False

    if job.has_filename:
        base = strip_trailing_date(job.new_filename, strict=False)
        target = _find_csv_by_name(source_folder, base, today_str)
        if target is None:
            logger.warning("'%s' を含む CSV が %s に見つかりません (No: %s)。スキップ。", base, source_folder, job.no)
            return False
    else:
        base = None
        target = _find_csv_by_date(source_folder, today_str)
        if target is None:
            logger.warning("今日の CSV が %s に見つかりません (No: %s)。スキップ。", source_folder, job.no)
            return False

    dest_name = (
        f"{job.report_id}_{base}_{today_str}.csv"
        if job.has_filename
        else f"{job.report_id}_{today_str}.csv"
    )
    destination = daily_output_folder / dest_name

    try:
        shutil.copy2(target, destination)
        logger.info("成功: From~ %s", target)
        return True
    except OSError as e:
        logger.error("コピー失敗 %s → %s: %s", target, destination, e)
        return False


def main() -> int:
    setup_logging()

    # --- setup ---
    try:
        jobs = read_jobs()
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    ids_path = find_latest_success_ids(OUTPUT_RESULTS_DIR)
    if ids_path is None:
        logger.error("success_ids ファイルが見つかりません。")
        return 1

    success_ids = read_ids_file(ids_path)
    logger.info("success IDs: %s (%d 件)", ids_path.name, len(success_ids))

    today_str = datetime.now().strftime("%Y%m%d")
    new_folder_name = _COLLECT_FOLDER_TEMPLATE.replace("#", today_str)
    daily_output_folder = CSV_STAGING_DIR / new_folder_name

    if daily_output_folder.is_dir():
        removed = [f for f in daily_output_folder.iterdir() if f.is_file()]
        for f in removed:
            f.unlink()
        if removed:
            logger.info("既存 %d 件を削除: %s", len(removed), daily_output_folder.name)

    daily_output_folder.mkdir(parents=True, exist_ok=True)

    # --- collect ---
    ok_count = 0
    failed_ids: list[str] = []

    for job in jobs:
        if job.report_id not in success_ids:
            continue
        if _collect_one_job(job, today_str, daily_output_folder):
            ok_count += 1
        else:
            failed_ids.append(job.report_id or job.no)

    # --- summary ---
    logger.info("*" * 50)
    logger.info("file_collect complete >>")
    logger.info("成功 %d 件 / 失敗 %d 件 / 合計 %d 件", ok_count, len(failed_ids), ok_count + len(failed_ids))
    if failed_ids:
        logger.info("-" * 50)
        for fid in failed_ids:
            logger.info("  %s", fid)
    logger.info("*" * 50)

    return 1 if failed_ids else 0


if __name__ == "__main__":
    sys.exit(main())
