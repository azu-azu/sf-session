"""dl_batch のエクスポートなし版 — ファイル振り分けスクリプト。

指定フォルダにある reportID_* ファイルを、
マクロファイルに記載の移動先フォルダへ振り分け（コピー）する。
リネーム指定がある場合はリネームも行う。

Usage:
    python sf-session/file_dispatch.py --source-dir outputs_csv
    python sf-session/file_dispatch.py --source-dir outputs_csv --dry-run
    python sf-session/file_dispatch.py --source-dir outputs_csv --date-suffix
    python sf-session/file_dispatch.py --source-dir outputs_csv --ids-file
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import DEFAULT_IDS_FILE, MACRO_DIR
from .macro_book_reader import JobEntry, load_active_jobs
from .utils import setup_logging

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
    *,
    date_suffix: bool,
) -> Path:
    """振り分け先パスを組み立てる。

    リネーム指定 (has_filename) があれば new_filename を使い、
    なければファイル名はそのまま維持する。
    """
    dest_dir = Path(job.src_folder_name)
    ext = source.suffix

    if job.has_filename:
        stem = job.new_filename
    else:
        stem = source.stem

    if date_suffix:
        today = datetime.now().strftime("%Y%m%d")
        stem = f"{stem}_{today}"

    return dest_dir / f"{stem}{ext}"


def distribute_files(
    source_dir: Path,
    jobs: list[JobEntry],
    *,
    date_suffix: bool = False,
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
        dest = build_destination(job, file, date_suffix=date_suffix)
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
    logger.info("file_dispatch complete >>")
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
        "--source-dir",
        type=Path,
        required=True,
        help="振り分け元フォルダ (reportID_* ファイルがある場所)",
    )
    parser.add_argument(
        "--macro-dir",
        type=Path,
        default=MACRO_DIR,
        help=f"マクロ格納フォルダ path (default: {MACRO_DIR})",
    )
    parser.add_argument(
        "--date-suffix",
        action="store_true",
        help="ファイル名に _YYYYMMDD を付与",
    )
    parser.add_argument(
        "--ids-file",
        action="store_true",
        default=False,
        help=f"{DEFAULT_IDS_FILE} から report ID を読み取り、intersection でフィルタ",
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
            dest = build_destination(job, file, date_suffix=args.date_suffix)
            logger.info("  %-50s → %s", file.name, dest)
        return 0

    logger.info("Source dir  : %s", source_dir)

    results = distribute_files(
        source_dir, active_jobs, date_suffix=args.date_suffix,
    )

    log_summary(results)

    failed = sum(1 for r in results if not r.success)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# Tests (run with: cd sf-session && python -m pytest file_dispatch.py -v)
# ---------------------------------------------------------------------------


def _make_job(**kwargs) -> JobEntry:
    """テスト用 JobEntry ファクトリ。"""
    defaults = dict(
        no="1",
        report_id="00O123",
        has_filename=False,
        new_filename="",
        src_folder_name="/tmp/dest",
        encode="UTF-8",
        skip="",
    )
    defaults.update(kwargs)
    return JobEntry(**defaults)


class TestBuildJobLookup:
    def test_builds_lookup(self):
        jobs = [_make_job(report_id="AAA"), _make_job(report_id="BBB")]
        lookup = build_job_lookup(jobs)
        assert set(lookup.keys()) == {"AAA", "BBB"}

    def test_skips_none_report_id(self):
        jobs = [_make_job(report_id=None), _make_job(report_id="BBB")]
        lookup = build_job_lookup(jobs)
        assert set(lookup.keys()) == {"BBB"}


class TestMatchFileToJob:
    def test_match(self):
        lookup = build_job_lookup([_make_job(report_id="00O123")])
        job = match_file_to_job("00O123_report.csv", lookup)
        assert job is not None
        assert job.report_id == "00O123"

    def test_no_match(self):
        lookup = build_job_lookup([_make_job(report_id="00O123")])
        assert match_file_to_job("00OOTHER_report.csv", lookup) is None

    def test_partial_id_no_match(self):
        lookup = build_job_lookup([_make_job(report_id="00O123")])
        assert match_file_to_job("00O12_report.csv", lookup) is None

    def test_requires_underscore_separator(self):
        lookup = build_job_lookup([_make_job(report_id="00O123")])
        assert match_file_to_job("00O123report.csv", lookup) is None


class TestBuildDestination:
    def test_no_filename_keeps_full_stem(self, tmp_path):
        job = _make_job(src_folder_name=str(tmp_path))
        source = tmp_path / "00O123_report.csv"
        source.touch()

        result = build_destination(job, source, date_suffix=False)
        assert result == tmp_path / "00O123_report.csv"

    def test_with_new_filename(self, tmp_path):
        job = _make_job(
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="daily_export",
        )
        source = tmp_path / "00O123_original.csv"
        source.touch()

        result = build_destination(job, source, date_suffix=False)
        assert result == tmp_path / "daily_export.csv"

    def test_with_date_suffix_no_filename(self, tmp_path):
        from unittest.mock import patch

        job = _make_job(src_folder_name=str(tmp_path))
        source = tmp_path / "00O123_report.csv"
        source.touch()

        with patch("sf_session.file_dispatch.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260319"
            result = build_destination(job, source, date_suffix=True)

        assert result == tmp_path / "00O123_report_20260319.csv"

    def test_with_new_filename_and_date_suffix(self, tmp_path):
        from unittest.mock import patch

        job = _make_job(
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="daily",
        )
        source = tmp_path / "00O123_original.xlsx"
        source.touch()

        with patch("sf_session.file_dispatch.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260319"
            result = build_destination(job, source, date_suffix=True)

        assert result == tmp_path / "daily_20260319.xlsx"

    def test_preserves_extension(self, tmp_path):
        job = _make_job(
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="output",
        )
        source = tmp_path / "00O123_data.xls"
        source.touch()

        result = build_destination(job, source, date_suffix=False)
        assert result == tmp_path / "output.xls"


class TestDistributeFiles:
    def test_moves_file_to_dest(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        f = src_dir / "00O123_report.csv"
        f.write_text("data")

        jobs = [_make_job(report_id="00O123", src_folder_name=str(dest_dir))]
        results = distribute_files(src_dir, jobs)

        assert len(results) == 1
        assert results[0].success
        assert results[0].dest_path == dest_dir / "00O123_report.csv"
        assert (dest_dir / "00O123_report.csv").exists()
        assert f.exists()  # コピーなので元ファイルは残る

    def test_renames_file(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        f = src_dir / "00O123_original.csv"
        f.write_text("data")

        jobs = [_make_job(
            report_id="00O123",
            src_folder_name=str(dest_dir),
            has_filename=True,
            new_filename="renamed",
        )]
        results = distribute_files(src_dir, jobs)

        assert len(results) == 1
        assert results[0].success
        assert results[0].dest_path == dest_dir / "renamed.csv"
        assert (dest_dir / "renamed.csv").exists()

    def test_dest_dir_missing(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()

        f = src_dir / "00O123_report.csv"
        f.write_text("data")

        jobs = [_make_job(
            report_id="00O123",
            src_folder_name=str(tmp_path / "nonexistent"),
        )]
        results = distribute_files(src_dir, jobs)

        assert len(results) == 1
        assert not results[0].success
        assert "振り分け先フォルダが存在しません" in results[0].error
        assert f.exists()  # 元ファイルはそのまま

    def test_no_match_skipped(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()

        (src_dir / "UNKNOWN_report.csv").write_text("data")

        jobs = [_make_job(report_id="00O123")]
        results = distribute_files(src_dir, jobs)

        assert len(results) == 0

    def test_multiple_files(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dest1 = tmp_path / "dest1"
        dest1.mkdir()
        dest2 = tmp_path / "dest2"
        dest2.mkdir()

        (src_dir / "00OAAA_report_a.csv").write_text("a")
        (src_dir / "00OBBB_report_b.csv").write_text("b")

        jobs = [
            _make_job(no="1", report_id="00OAAA", src_folder_name=str(dest1)),
            _make_job(no="2", report_id="00OBBB", src_folder_name=str(dest2)),
        ]
        results = distribute_files(src_dir, jobs)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert (dest1 / "00OAAA_report_a.csv").exists()
        assert (dest2 / "00OBBB_report_b.csv").exists()

    def test_directories_ignored(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "00O123_subdir").mkdir()

        jobs = [_make_job(report_id="00O123")]
        results = distribute_files(src_dir, jobs)
        assert len(results) == 0


class TestLogSummary:
    def test_all_success(self, caplog):
        results = [
            DistributeResult(
                seq=1, report_id="00O1", source_name="00O1_r.csv",
                success=True, dest_path=Path("/out/r.csv"),
            ),
        ]
        with caplog.at_level(logging.INFO):
            log_summary(results)
        assert "成功 1 件" in caplog.text

    def test_with_failures(self, caplog):
        results = [
            DistributeResult(
                seq=1, report_id="00O1", source_name="00O1_r.csv",
                success=True, dest_path=Path("/out/r.csv"),
            ),
            DistributeResult(
                seq=2, report_id="00O2", source_name="00O2_r.csv",
                success=False, error="振り分け先フォルダが存在しません",
            ),
        ]
        with caplog.at_level(logging.INFO):
            log_summary(results)
        assert "成功 1 件" in caplog.text
        assert "失敗 1 件" in caplog.text


class TestParseArgs:
    def test_source_dir_required(self):
        import pytest

        with pytest.raises(SystemExit):
            parse_args([])

    def test_source_dir(self):
        args = parse_args(["--source-dir", "/tmp/src"])
        assert args.source_dir == Path("/tmp/src")

    def test_defaults(self):
        args = parse_args(["--source-dir", "/tmp/src"])
        assert not args.date_suffix
        assert not args.dry_run
        assert not args.ids_file
        assert args.macro_dir == MACRO_DIR

    def test_all_flags(self):
        args = parse_args([
            "--source-dir", "/tmp/src",
            "--date-suffix",
            "--ids-file",
            "--dry-run",
            "--macro-dir", "/tmp/macro",
        ])
        assert args.date_suffix
        assert args.ids_file
        assert args.dry_run
        assert args.macro_dir == Path("/tmp/macro")
