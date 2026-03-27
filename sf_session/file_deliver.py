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
from dataclasses import dataclass
from pathlib import Path

from .config import ARCHIVE_CSV_DIR, ARCHIVE_IDS_FILE, ARCHIVE_MACRO_DIR, PROJECT_ROOT, VALID_PIPELINES
from .macro_book_reader import JobEntry, load_active_jobs
from .utils import build_output_stem, setup_logging, time_label, write_pipeline_status

logger = logging.getLogger(__name__)


@dataclass
class DistributeResult:
    """1ファイルの振り分け結果。"""

    seq: int
    report_id: str
    source_name: str
    success: bool
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


def build_destination(
    job: JobEntry,
    source: Path,
) -> Path:
    """振り分け先パスを組み立てる。

    ファイル名は {report_id}_{YYYYMMDD}_{stem}{ext} 形式。
    リネーム指定 (has_filename) があれば stem = new_filename、なければ元ファイル名。
    """
    dest_dir = Path(job.src_folder_name)
    ext = source.suffix
    raw_stem = job.new_filename if job.has_filename else source.stem
    stem = build_output_stem(job.report_id, raw_stem)

    return dest_dir / f"{stem}{ext}"


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
        dest = build_destination(job, file)
        dest_dir = dest.parent

        if not dest_dir.is_dir():
            results.append(DistributeResult(
                seq=count,
                report_id=job.report_id or "",
                source_name=file.name,
                success=False,
                error=f"振り分け先フォルダが存在しません: {dest_dir}",
            ))
            continue

        try:
            shutil.copy2(str(file), str(dest))
            logger.info("[%d件目] %s  %s → %s", count, job.report_id, file.name, dest)
            results.append(DistributeResult(
                seq=count,
                report_id=job.report_id or "",
                source_name=file.name,
                success=True,
                dest_path=dest,
            ))
        except OSError as e:
            results.append(DistributeResult(
                seq=count,
                report_id=job.report_id or "",
                source_name=file.name,
                success=False,
                error=f"コピー失敗: {e}",
            ))

    return results


def log_summary(results: list[DistributeResult]) -> None:
    """実行結果のサマリーをログ出力する。"""
    ok = sum(1 for r in results if r.success)
    ng = sum(1 for r in results if not r.success)

    logger.info("*" * 50)
    logger.info("file_deliver complete >>")
    logger.info("成功 %d 件 / 失敗 %d 件 / 合計 %d 件", ok, ng, len(results))
    logger.info("-" * 50)

    for r in results:
        status = "OK" if r.success else "NG"
        dest = r.dest_path or "-"
        err = f" ({r.error})" if r.error else ""
        logger.info(
            "  [%s] %d件目 %s  %s → %s%s",
            status, r.seq, r.report_id, r.source_name, dest, err,
        )

    logger.info("*" * 50)


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
        default=ARCHIVE_CSV_DIR,
        help=f"振り分け元フォルダ (default: {ARCHIVE_CSV_DIR})",
    )
    parser.add_argument(
        "--macro-dir",
        type=Path,
        default=ARCHIVE_MACRO_DIR,
        help=f"マクロ格納フォルダ path (default: {ARCHIVE_MACRO_DIR})",
    )
    parser.add_argument(
        "--ids-file",
        action="store_true",
        default=False,
        help=f"{ARCHIVE_IDS_FILE} から report ID を読み取り、intersection でフィルタ",
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

    source_dir = args.source_dir.expanduser().resolve()
    if not source_dir.is_dir():
        logger.error("source-dir が存在しません: %s", source_dir)
        return 1

    try:
        active_jobs = load_active_jobs(args.macro_dir, ids_file=args.ids_file)
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
        for file in sorted(source_dir.iterdir()):
            if not file.is_file():
                continue
            job = match_file_to_job(file.name, lookup)
            if job is None:
                logger.info("  %-50s → (マッチなし)", file.name)
                continue
            dest = build_destination(job, file)
            logger.info("  %-50s → %s", file.name, dest)
        return 0

    logger.info("Source dir  : %s", source_dir)

    results = distribute_files(source_dir, active_jobs)

    log_summary(results)

    # 完了マーカー
    marker = source_dir / f"_{time_label()}_振り分け完了.txt"
    marker.touch()
    logger.info("完了マーカー: %s", marker.name)

    write_pipeline_status(
        PROJECT_ROOT, args.pipeline, "dv",
        f"{time_label()}_振り分け完了",
    )

    failed = sum(1 for r in results if not r.success)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
