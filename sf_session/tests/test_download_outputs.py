"""download_outputs のテスト。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from sf_session.download.outputs import (
    build_destination,
    log_summary,
    probe_output_dir,
    prepare_work_dir,
    swap_work_to_staging,
    write_marker,
    write_start_marker,
    write_success_ids,
)
from sf_session.download.runner import ExportResult
from sf_session.tests.helpers import make_job


class TestBuildDestination:
    def test_no_filename_no_suffix(self, tmp_path):
        job = make_job(src_folder_name=str(tmp_path))
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        result = build_destination(job, downloaded, date_suffix=False)
        assert result == tmp_path / "report.csv"

    def test_with_filename(self, tmp_path):
        job = make_job(
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="myreport",
        )
        downloaded = tmp_path / "original.csv"
        downloaded.touch()

        result = build_destination(job, downloaded, date_suffix=False)
        assert result == tmp_path / "myreport.csv"

    def test_with_date_suffix(self, tmp_path):
        job = make_job(src_folder_name=str(tmp_path))
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260317"
            result = build_destination(job, downloaded, date_suffix=True)

        assert result == tmp_path / "report_20260317.csv"

    def test_with_filename_and_date_suffix(self, tmp_path):
        job = make_job(
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="daily",
        )
        downloaded = tmp_path / "original.xlsx"
        downloaded.touch()

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260317"
            result = build_destination(job, downloaded, date_suffix=True)

        assert result == tmp_path / "daily_20260317.xlsx"

    def test_preserves_download_extension(self, tmp_path):
        job = make_job(
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="output",
        )
        downloaded = tmp_path / "data.xls"
        downloaded.touch()

        result = build_destination(job, downloaded, date_suffix=False)
        assert result == tmp_path / "output.xls"

    def test_output_dir_prefixes_report_id(self, tmp_path):
        out_dir = tmp_path / "outputs_csv"
        out_dir.mkdir()
        job = make_job(report_id="00O999")
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        result = build_destination(
            job, downloaded, date_suffix=False, output_dir=out_dir,
        )
        assert result == out_dir / "00O999_report.csv"

    def test_output_dir_with_new_filename(self, tmp_path):
        out_dir = tmp_path / "outputs_csv"
        out_dir.mkdir()
        job = make_job(
            report_id="00O999",
            has_filename=True,
            new_filename="daily",
        )
        downloaded = tmp_path / "original.csv"
        downloaded.touch()

        result = build_destination(
            job, downloaded, date_suffix=False, output_dir=out_dir,
        )
        assert result == out_dir / "00O999_daily.csv"

    def test_output_dir_with_date_suffix(self, tmp_path):
        out_dir = tmp_path / "outputs_csv"
        out_dir.mkdir()
        job = make_job(report_id="00O999")
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260318"
            result = build_destination(
                job, downloaded, date_suffix=True, output_dir=out_dir,
            )

        assert result == out_dir / "00O999_report_20260318.csv"


class TestLogSummary:
    def test_no_error(self, caplog):
        results = [
            ExportResult(
                seq=1, report_id="00O1", success=True,
                elapsed=1.5, dest_path=Path("/out/r.csv"),
            ),
        ]
        with caplog.at_level(logging.INFO):
            log_summary(results)
        assert "成功 1 件" in caplog.text

    def test_with_failures(self, caplog):
        results = [
            ExportResult(
                seq=1, report_id="00O1", success=True,
                elapsed=1.5, dest_path=Path("/out/r.csv"),
            ),
            ExportResult(
                seq=2, report_id="00O2", success=False,
                elapsed=10.0, error="timeout",
            ),
        ]
        with caplog.at_level(logging.INFO):
            log_summary(results)
        assert "成功 1 件" in caplog.text
        assert "失敗 1 件" in caplog.text


class TestWriteSuccessIds:
    def test_writes_success_ids(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sf_session.download.outputs.OUTPUT_RESULTS_DIR", tmp_path)
        results = [
            ExportResult(seq=1, report_id="00O001", success=True, elapsed=1.0),
            ExportResult(seq=2, report_id="00O002", success=False, elapsed=2.0),
            ExportResult(seq=3, report_id="00O003", success=True, elapsed=1.5),
        ]

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260321"
            path = write_success_ids(results)

        assert path == tmp_path / "success_ids_20260321.txt"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert lines == ["00O001", "00O003"]

    def test_no_success_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sf_session.download.outputs.OUTPUT_RESULTS_DIR", tmp_path)
        results = [
            ExportResult(seq=1, report_id="00O001", success=False, elapsed=1.0),
        ]
        assert write_success_ids(results) is None

    def test_creates_dir_if_missing(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "outputs_result"
        monkeypatch.setattr("sf_session.download.outputs.OUTPUT_RESULTS_DIR", out_dir)
        results = [
            ExportResult(seq=1, report_id="00O001", success=True, elapsed=1.0),
        ]

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260321"
            path = write_success_ids(results)

        assert out_dir.is_dir()
        assert path is not None
        assert path.exists()


class TestProbeOutputDir:
    def test_valid_dir(self, tmp_path):
        probe_output_dir(tmp_path)  # should not raise

    def test_nonexistent_dir(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="出力先ディレクトリが存在しません"):
            probe_output_dir(tmp_path / "nonexistent")

    def test_readonly_dir(self, tmp_path, monkeypatch):
        """touch が OSError を raise するケース。"""
        target = tmp_path / "readonly"
        target.mkdir()

        def mock_touch(self):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "touch", mock_touch)
        with pytest.raises(OSError, match="書き込めません"):
            probe_output_dir(target)


class TestPrepareWorkDir:
    def test_creates_new(self, tmp_path):
        staging = tmp_path / "outputs_csv"
        work = prepare_work_dir(staging)
        assert re.match(r"outputs_csv_work_\d{8}_\d{6}$", work.name)
        assert work.is_dir()


class TestWriteStartMarker:
    def test_creates_start_marker(self, tmp_path):
        marker = write_start_marker(tmp_path, 5)
        assert marker.exists()
        assert "START" in marker.name
        assert "5件の予定" in marker.name


class TestWriteMarker:
    def test_creates_marker(self, tmp_path):
        marker = write_marker(tmp_path, 3, 1)
        assert marker.exists()
        assert "成功3件" in marker.name
        assert "失敗1件" in marker.name


class TestSwapWorkToStaging:
    def test_normal_swap(self, tmp_path):
        staging = tmp_path / "outputs_csv"
        work = tmp_path / "outputs_csv_work_20260326_120000"
        work.mkdir()
        (work / "new.csv").write_text("new")

        swap_work_to_staging(work, staging, ok_count=1)

        assert staging.is_dir()
        assert (staging / "new.csv").read_text() == "new"
        assert not work.exists()

    def test_prev_backup(self, tmp_path):
        staging = tmp_path / "outputs_csv"
        staging.mkdir()
        (staging / "old.csv").write_text("old")
        work = tmp_path / "outputs_csv_work_20260326_120000"
        work.mkdir()
        (work / "new.csv").write_text("new")

        swap_work_to_staging(work, staging, ok_count=1)

        prevs = list(tmp_path.glob("outputs_csv_prev_*"))
        assert len(prevs) == 1
        assert (prevs[0] / "old.csv").read_text() == "old"

    def test_cleanup_removes_old_prev(self, tmp_path):
        """古い _prev_* が swap 前に削除される。"""
        staging = tmp_path / "outputs_csv"
        staging.mkdir()

        # 古い prev を2つ作成
        old_prev1 = tmp_path / "outputs_csv_prev_20260101_000000"
        old_prev1.mkdir()
        (old_prev1 / "ancient.csv").write_text("ancient")
        old_prev2 = tmp_path / "outputs_csv_prev_20260201_000000"
        old_prev2.mkdir()

        work = tmp_path / "outputs_csv_work_20260326_120000"
        work.mkdir()
        (work / "new.csv").write_text("new")

        swap_work_to_staging(work, staging, ok_count=1)

        # 古い prev は消えて、今回の prev だけ残る
        prevs = sorted(tmp_path.glob("outputs_csv_prev_*"))
        assert len(prevs) == 1
        assert not (prevs[0] / "ancient.csv").exists()

    def test_zero_success_no_swap(self, tmp_path):
        staging = tmp_path / "outputs_csv"
        staging.mkdir()
        (staging / "keep.csv").write_text("keep")
        work = tmp_path / "outputs_csv_work_20260326_120000"
        work.mkdir()

        swap_work_to_staging(work, staging, ok_count=0)

        assert (staging / "keep.csv").read_text() == "keep"
        assert work.is_dir()  # swap されない
