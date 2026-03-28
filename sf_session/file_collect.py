"""macro_book_reader のジョブ定義と success ID で対象 CSV を特定し、日付フォルダへコピーする。

file_deliver の逆操作: 各フォルダから CSV を収集して pipeline の csv_dir に集約する。

Usage:
    python -m sf_session.file_collect archive
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import PIPELINES, VALID_PIPELINES
from .macro_book_reader import JobEntry, read_jobs
from .utils import (
    build_output_stem,
    find_latest_success_ids,
    read_ids_file,
    setup_logging,
    strip_trailing_date,
)

logger = logging.getLogger(__name__)

_COLLECT_FOLDER_TEMPLATE = "#_jis"


@dataclass
class CollectResult:
    """1ファイルの収集結果。"""

    seq: int
    report_id: str
    success: bool
    elapsed: float = 0.0
    source_path: Path | None = None
    error: str = ""


def _extract_raw_stem(stem: str, report_id: str | None, today_str: str) -> str:
    """ファイル名の stem から report_id prefix と日付を除いた raw stem を返す。"""
    # 新命名: {report_id}_{YYYYMMDD}_{raw_stem}
    if report_id:
        new_prefix = f"{report_id}_{today_str}_"
        if stem.startswith(new_prefix):
            return stem[len(new_prefix):]
    # 旧命名: {raw_stem}_{YYYYMMDD}
    old_suffix = f"_{today_str}"
    if stem.endswith(old_suffix):
        return stem[: -len(old_suffix)]
    return stem


def _dump_csv_list(csvs: list[Path]) -> None:
    """フォルダ内の CSV ファイルと mtime を出力する（検索失敗時の診断用）。"""
    lines = [
        f"  {p.name}  mtime={datetime.fromtimestamp(p.stat().st_mtime)}"
        for p in csvs[:10]
    ]
    if len(csvs) > 10:
        lines.append(f"  ... 他 {len(csvs) - 10} 件")
    logger.debug("フォルダ内の CSV:\n%s", "\n".join(lines))


def _find_csv_by_name(
    source_folder: Path,
    name_fragment: str,
    today_str: str,
    report_id: str | None = None,
) -> Path | None:
    """指定されたベース名 + 今日の日付の CSV を優先的に返す。

    Network drive では mtime が信用できないため、ファイル名の日付を優先する。
    """
    csvs = list(source_folder.glob("*.csv"))

    # 新命名: {report_id}_{YYYYMMDD}_{name}.csv
    if report_id:
        new_exact = f"{report_id}_{today_str}_{name_fragment}.csv"
        for p in csvs:
            if p.name == new_exact:
                return p

    # 旧命名: {name}_{YYYYMMDD}.csv
    old_exact = f"{name_fragment}_{today_str}.csv"
    for p in csvs:
        if p.name == old_exact:
            return p

    # fallback: name_fragment を含む CSV のうち mtime 最新
    matches = [p for p in csvs if name_fragment in p.name]
    if not matches:
        if csvs:
            _dump_csv_list(csvs)
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _find_csv_by_date(
    source_folder: Path,
    today_str: str,
    report_id: str | None = None,
) -> Path | None:
    """今日の日付を含む CSV を検索する。"""
    csvs = list(source_folder.glob("*.csv"))

    # 新命名: {report_id}_{YYYYMMDD}_*.csv
    if report_id:
        prefix = f"{report_id}_{today_str}_"
        matches = [p for p in csvs if p.name.startswith(prefix)]
        if matches:
            return matches[0] if len(matches) == 1 else max(matches, key=lambda p: p.stat().st_mtime)

    # 旧命名: *_{YYYYMMDD}.csv
    for p in csvs:
        if p.name.lower().endswith(f"{today_str}.csv"):
            return p

    # fallback: mtime が今日の CSV
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
    *,
    seq: int,
) -> CollectResult:
    """1ジョブ分の CSV を検索・コピーする。"""
    report_id = job.report_id or job.no
    source_folder = Path(job.src_folder_name)
    t0 = time.monotonic()

    if not source_folder.is_dir():
        logger.warning("フォルダが見つかりません: %s (No: %s)。スキップ。", source_folder, job.no)
        return CollectResult(
            seq=seq, report_id=report_id, success=False,
            elapsed=time.monotonic() - t0, error="フォルダが見つかりません",
        )

    if job.has_filename:
        base = strip_trailing_date(job.new_filename, strict=False)
        target = _find_csv_by_name(source_folder, base, today_str, job.report_id)
        if target is None:
            logger.warning("'%s' を含む CSV が %s に見つかりません (No: %s)。スキップ。", base, source_folder, job.no)
            return CollectResult(
                seq=seq, report_id=report_id, success=False,
                elapsed=time.monotonic() - t0, error="CSV が見つかりません",
            )
        raw_stem = base
    else:
        target = _find_csv_by_date(source_folder, today_str, job.report_id)
        if target is None:
            logger.warning("今日の CSV が %s に見つかりません (No: %s)。スキップ。", source_folder, job.no)
            return CollectResult(
                seq=seq, report_id=report_id, success=False,
                elapsed=time.monotonic() - t0, error="CSV が見つかりません",
            )
        raw_stem = _extract_raw_stem(target.stem, job.report_id, today_str)

    dest_name = f"{build_output_stem(job.report_id, raw_stem)}{target.suffix}"
    destination = daily_output_folder / dest_name

    try:
        shutil.copy2(target, destination)
        elapsed = time.monotonic() - t0
        logger.info("[%d件目] 収集完了: From %s", seq, target)
        return CollectResult(
            seq=seq, report_id=report_id, success=True,
            elapsed=elapsed, source_path=target,
        )
    except OSError as e:
        elapsed = time.monotonic() - t0
        logger.error("コピー失敗 %s → %s: %s", target, destination, e)
        return CollectResult(
            seq=seq, report_id=report_id, success=False,
            elapsed=elapsed, error=f"コピー失敗: {e}",
        )


def log_summary(results: list[CollectResult]) -> None:
    """実行結果のサマリーをログ出力する。"""
    ok = sum(1 for r in results if r.success)
    ng = sum(1 for r in results if not r.success)

    logger.info("*" * 50)
    logger.info("file_collect complete >>")
    logger.info("成功 %d 件 / 失敗 %d 件 / 合計 %d 件", ok, ng, len(results))

    failures = [r for r in results if not r.success]
    if failures:
        logger.info("-" * 50)
        for r in failures:
            source = f"From {r.source_path}" if r.source_path else "-"
            err = f" ({r.error})" if r.error else ""
            logger.info(
                "  [NG] %d件目 %s  %.1fs  %s%s",
                r.seq, r.report_id, r.elapsed, source, err,
            )

    logger.info("*" * 50)


def _dry_run_preview(
    jobs: list[JobEntry],
    success_ids: set[str],
    today_str: str,
) -> None:
    """dry-run: 各 job の収集元 CSV をプレビュー表示する。"""
    logger.info("--- dry-run mode ---")
    seq = 0
    for job in jobs:
        if job.report_id not in success_ids:
            continue
        seq += 1
        report_id = job.report_id or job.no
        source_folder = Path(job.src_folder_name)

        if not source_folder.is_dir():
            logger.info("  [%d件目] %s → (フォルダなし: %s)", seq, report_id, source_folder)
            continue

        if job.has_filename:
            base = strip_trailing_date(job.new_filename, strict=False)
            target = _find_csv_by_name(source_folder, base, today_str, job.report_id)
        else:
            target = _find_csv_by_date(source_folder, today_str, job.report_id)

        if target is None:
            logger.info("  [%d件目] %s → (CSV なし: %s)", seq, report_id, source_folder)
        else:
            logger.info("  [%d件目] %s → From %s", seq, report_id, target)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ジョブ定義と success ID で対象 CSV を収集する",
    )
    parser.add_argument(
        "pipeline",
        choices=VALID_PIPELINES,
        help="実行対象の pipeline 名",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実行せず収集対象のプレビューを表示",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()

    args = parse_args(argv)
    pipeline = PIPELINES[args.pipeline]

    # --- setup ---
    try:
        jobs = read_jobs(pipeline.macro_dir)
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    ids_path = find_latest_success_ids(pipeline.result_dir)
    if ids_path is None:
        logger.error("success_ids ファイルが見つかりません。")
        return 1

    success_ids = read_ids_file(ids_path)
    logger.info("success IDs: %s (%d 件)", ids_path.name, len(success_ids))

    today_str = datetime.now().strftime("%Y%m%d")

    if args.dry_run:
        _dry_run_preview(jobs, success_ids, today_str)
        return 0

    new_folder_name = _COLLECT_FOLDER_TEMPLATE.replace("#", today_str)
    daily_output_folder = pipeline.csv_dir / new_folder_name

    if daily_output_folder.is_dir():
        removed = [f for f in daily_output_folder.iterdir() if f.is_file()]
        for f in removed:
            f.unlink()
        if removed:
            logger.info("既存 %d 件を削除: %s", len(removed), daily_output_folder.name)

    daily_output_folder.mkdir(parents=True, exist_ok=True)

    # --- collect ---
    results: list[CollectResult] = []
    seq = 0

    for job in jobs:
        if job.report_id not in success_ids:
            continue
        seq += 1
        results.append(
            _collect_one_job(job, today_str, daily_output_folder, seq=seq),
        )

    # --- summary ---
    log_summary(results)

    failed = sum(1 for r in results if not r.success)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
