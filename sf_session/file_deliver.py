"""download のエクスポートなし版 — ファイル振り分けスクリプト。

指定フォルダにある reportID_* ファイルを、
マクロファイルに記載の移動先フォルダへ振り分け（コピー）する。
リネーム指定がある場合はリネームも行う。

Usage:
    python -m sf_session.file_deliver archive
    python -m sf_session.file_deliver archive --dry-run
    python -m sf_session.file_deliver archive --ids-file
    python -m sf_session.file_deliver archive --source-dir /other/path
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from dataclasses import dataclass, replace as _dc_replace
from pathlib import Path

from .config import PIPELINES, VALID_PIPELINES, OUTPUT_ROOT, resolve_project_path
from .download.outputs import build_destination, probe_destinations
from .macro_book_reader import JobEntry, load_active_jobs
from .pipeline_status import log_result_summary, write_pipeline_status
from .utils import setup_logging, time_label

logger = logging.getLogger(__name__)


@dataclass
class DistributeResult:
    """1ファイルの振り分け結果。"""

    seq: int
    report_id: str
    success: bool
    elapsed: float = 0.0
    dest_path: Path | None = None
    error: str = ""


def build_job_lookup(jobs: list[JobEntry]) -> dict[str, JobEntry]:
    """report_id → JobEntry の lookup dict を構築する。"""
    lookup: dict[str, JobEntry] = {}
    for job in jobs:
        if job.report_id:
            lookup[job.report_id] = job
    return lookup


def match_file_to_job(
    filename: str,
    lookup: dict[str, JobEntry],
) -> JobEntry | None:
    """ファイル名の先頭 ``{reportID}_`` から対応する JobEntry を返す。"""
    for report_id, job in lookup.items():
        if filename.startswith(f"{report_id}_"):
            return job
    return None


def _collect_target_jobs(source_dir: Path, lookup: dict[str, JobEntry]) -> list[JobEntry]:
    """source_dir に実在するファイルとマッチした job だけを返す。"""
    selected: dict[str, JobEntry] = {}

    for file in sorted(source_dir.iterdir()):
        if not file.is_file():
            continue

        job = match_file_to_job(file.name, lookup)
        if job is None or not job.report_id:
            continue
        
        selected[job.report_id] = job

    return list(selected.values())


def distribute_files(
    source_dir: Path,
    jobs: list[JobEntry],
) -> list[DistributeResult]:
    """source_dir 内のファイルを jobs に基づいて振り分ける。"""
    lookup = build_job_lookup(jobs)
    results: list[DistributeResult] = []
    count = 0

    for file in sorted(source_dir.iterdir()):
        if not file.is_file():
            continue

        job = match_file_to_job(file.name, lookup)
        if job is None:
            logger.warning("マッチするジョブなし: %s", file.name)
            continue

        count += 1
        dest = build_destination(job, file, mode="file_deliver")
        dest_dir = dest.parent
        t0 = time.monotonic()

        if not dest_dir.is_dir():
            results.append(DistributeResult(
                seq=count,
                report_id=job.report_id or "",
                success=False,
                elapsed=time.monotonic() - t0,
                error=f"振り分け先フォルダが存在しません: {dest_dir}",
            ))
            continue
        try:
            shutil.copy2(str(file), str(dest))
            elapsed = time.monotonic() - t0
            logger.info("[%d件目] 移動完了", count)
            results.append(DistributeResult(
                seq=count,
                report_id=job.report_id or "",
                success=True,
                elapsed=elapsed,
                dest_path=dest,
            ))
        except OSError as e:
            elapsed = time.monotonic() - t0
            results.append(DistributeResult(
                seq=count,
                report_id=job.report_id or "",
                success=False,
                elapsed=elapsed,
                error=f"コピー失敗: {e}",
            ))

    return results


def log_summary(results: list[DistributeResult]) -> None:
    """実行結果のサマリーをログ出力する。"""
    log_result_summary(
        results, 
        "file_deliver",
        show_successes=True,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="reportID_* ファイルをマクロ定義に基づき振り分け先フォルダへコピーする",
    )
    parser.add_argument(
        "pipeline",
        choices=VALID_PIPELINES,
        help="実行対象の pipeline 名",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="振り分け元フォルダ (default: pipeline config)",
    )
    parser.add_argument(
        "--macro-dir",
        type=Path,
        default=None,
        help="マクロ格納フォルダ path (default: pipeline config)",
    )
    parser.add_argument(
        "--ids-file",
        action="store_true",
        default=False,
        help="ids.txt から report ID を読み取り、intersection でフィルタ",
    )
    parser.add_argument(
        "--mkdir",
        action="store_true",
        help="移動先フォルダが存在しない場合、親があれば最終フォルダを自動作成",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実行せず振り分け先のプレビューを表示",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()

    args = parse_args(argv)
    assert OUTPUT_ROOT is not None  # validated by _load_pipelines
    pipeline = PIPELINES[args.pipeline]

    source_dir = resolve_project_path(args.source_dir or pipeline.csv_dir)
    if not source_dir.is_dir():
        logger.error("source-dir が存在しません: %s", source_dir)
        return 1

    effective = (
        _dc_replace(pipeline, macro_dir=resolve_project_path(args.macro_dir))
        if args.macro_dir 
        else pipeline
    )
    try:
        active_jobs = load_active_jobs(effective, ids_file=args.ids_file)
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    if not active_jobs:
        logger.info("実行対象のジョブが 0 件のため終了します")
        return 0

    lookup = build_job_lookup(active_jobs)

    if args.dry_run:
        logger.info("Source dir  : %s", source_dir)
        logger.info("--- dry-run mode ---")
        seq = 0
        for file in sorted(source_dir.iterdir()):
            if not file.is_file():
                continue
            job = match_file_to_job(file.name, lookup)
            if job is None:
                logger.info("  %s → (マッチなし)", file.name)
                continue
            seq += 1
            dest = build_destination(job, file, mode="file_deliver")
            logger.info("  [%d件目] %s → %s", seq, file.name, dest)
        return 0

    target_jobs = _collect_target_jobs(source_dir, lookup)

    errors = probe_destinations(target_jobs, mkdir=args.mkdir)
    if errors:
        for msg in errors:
            logger.error("振り分け先フォルダの判定に問題が発生: %s", msg)
        return 1

    logger.info("Source dir  : %s", source_dir)

    results = distribute_files(source_dir, active_jobs)

    log_summary(results)

    # 完了マーカー
    marker = source_dir / f"★{time_label()}_振り分け完了.txt"
    marker.touch()
    logger.info("完了マーカー: %s", marker.name)

    write_pipeline_status(
        OUTPUT_ROOT.parent, args.pipeline, "dv",
        f"{time_label()}_振り分け完了",
    )

    failed = sum(1 for r in results if not r.success)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
