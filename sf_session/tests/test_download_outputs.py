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
    probe_destinations,
    probe_output_dir,
    prepare_work_dir,
    swap_work_to_staging,
    write_completion_marker,
    write_start_marker,
    write_success_ids,
)
from sf_session.download.runner import ExportResult
from sf_session.tests.helpers import make_job


class TestBuildDestination:
    def test_no_filename(self, tmp_path):
        job = make_job(report_id="00O123", src_folder_name=str(tmp_path))
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, downloaded, mode="download")

        assert result == tmp_path / "00O123_20260327.csv"

    def test_with_filename(self, tmp_path):
        job = make_job(
            report_id="00O123",
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="myreport",
        )
        downloaded = tmp_path / "original.csv"
        downloaded.touch()

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, downloaded, mode="download")

        assert result == tmp_path / "00O123_20260327_myreport.csv"

    def test_preserves_download_extension(self, tmp_path):
        job = make_job(
            report_id="00O123",
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="output",
        )
        downloaded = tmp_path / "data.xls"
        downloaded.touch()

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, downloaded, mode="download")

        assert result == tmp_path / "00O123_20260327_output.xls"

    def test_output_dir(self, tmp_path):
        out_dir = tmp_path / "outputs_csv"
        out_dir.mkdir()
        job = make_job(report_id="00O999")
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, downloaded, mode="download", output_dir=out_dir)

        assert result == out_dir / "00O999_20260327.csv"

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

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, downloaded, mode="download", output_dir=out_dir)

        assert result == out_dir / "00O999_20260327_daily.csv"

    def test_no_report_id(self, tmp_path):
        """report_id が空なら prefix なし。"""
        job = make_job(report_id="", src_folder_name=str(tmp_path))
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        result = build_destination(job, downloaded, mode="download")
        assert result == tmp_path / "report.csv"

    def test_download_direct_with_filename(self, tmp_path):
        """download_direct + rename=yes: report_id なしで {new}_{YYYYMMDD}。"""
        job = make_job(
            report_id="00O123",
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="myreport",
        )
        downloaded = tmp_path / "original.csv"
        downloaded.touch()

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, downloaded, mode="download_direct")

        assert result == tmp_path / "myreport_20260327.csv"

    def test_download_direct_no_filename(self, tmp_path):
        """download_direct + rename=no: download と同じ {id}_{YYYYMMDD}_{stem}。"""
        job = make_job(report_id="00O123", src_folder_name=str(tmp_path))
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, downloaded, mode="download_direct")

        assert result == tmp_path / "00O123_20260327.csv"


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
    def test_writes_success_ids(self, tmp_path):
        result_dir = tmp_path / "result"
        results = [
            ExportResult(seq=1, report_id="00O001", success=True, elapsed=1.0),
            ExportResult(seq=2, report_id="00O002", success=False, elapsed=2.0),
            ExportResult(seq=3, report_id="00O003", success=True, elapsed=1.5),
        ]

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260321"
            path = write_success_ids(results, result_dir=result_dir)

        assert path == result_dir / "success_ids_20260321.txt"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert lines == ["00O001", "00O003"]

    def test_no_success_returns_none(self, tmp_path):
        result_dir = tmp_path / "result"
        results = [
            ExportResult(seq=1, report_id="00O001", success=False, elapsed=1.0),
        ]
        assert write_success_ids(results, result_dir=result_dir) is None

    def test_creates_dir_if_missing(self, tmp_path):
        result_dir = tmp_path / "outputs_result"
        results = [
            ExportResult(seq=1, report_id="00O001", success=True, elapsed=1.0),
        ]

        with patch("sf_session.download.outputs.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260321"
            path = write_success_ids(results, result_dir=result_dir)

        assert result_dir.is_dir()
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


class TestProbeOutputDirMkdir:
    def test_mkdir_creates_last_folder(self, tmp_path):
        target = tmp_path / "new_folder"
        assert not target.exists()
        probe_output_dir(target, mkdir=True)
        assert target.is_dir()

    def test_mkdir_parent_missing_raises(self, tmp_path):
        target = tmp_path / "missing_parent" / "child"
        with pytest.raises(FileNotFoundError, match="出力先ディレクトリが存在しません"):
            probe_output_dir(target, mkdir=True)

    def test_mkdir_false_does_not_create(self, tmp_path):
        target = tmp_path / "new_folder"
        with pytest.raises(FileNotFoundError):
            probe_output_dir(target, mkdir=False)
        assert not target.exists()

    def test_mkdir_path_is_file_raises(self, tmp_path):
        target = tmp_path / "not_a_dir"
        target.write_text("I am a file")
        with pytest.raises(FileNotFoundError, match="ファイルとして存在します"):
            probe_output_dir(target, mkdir=True)


class TestProbeDestinations:
    def test_all_accessible(self, tmp_path):
        d1 = tmp_path / "dest1"
        d1.mkdir()
        d2 = tmp_path / "dest2"
        d2.mkdir()
        jobs = [
            make_job(report_id="A", src_folder_name=str(d1)),
            make_job(report_id="B", src_folder_name=str(d2)),
        ]
        assert probe_destinations(jobs) == []

    def test_nonexistent_folder(self, tmp_path):
        jobs = [
            make_job(report_id="A", src_folder_name=str(tmp_path / "missing")),
        ]
        errors = probe_destinations(jobs)
        assert len(errors) == 1
        assert "存在しません" in errors[0]

    def test_empty_src_folder_name_skipped(self, tmp_path):
        jobs = [make_job(report_id="A", src_folder_name="")]
        assert probe_destinations(jobs) == []

    def test_duplicate_folder_probed_once(self, tmp_path):
        d = tmp_path / "dest"
        d.mkdir()
        jobs = [
            make_job(report_id="A", src_folder_name=str(d)),
            make_job(report_id="B", src_folder_name=str(d)),
        ]
        with patch.object(Path, "is_dir", wraps=d.is_dir) as mock_is_dir:
            probe_destinations(jobs)
        # probe_output_dir calls is_dir once per unique folder
        assert mock_is_dir.call_count == 1

    def test_multiple_errors_collected(self, tmp_path):
        jobs = [
            make_job(report_id="A", src_folder_name=str(tmp_path / "m1")),
            make_job(report_id="B", src_folder_name=str(tmp_path / "m2")),
        ]
        errors = probe_destinations(jobs)
        assert len(errors) == 2

    def test_mkdir_creates_missing_folders(self, tmp_path):
        d1 = tmp_path / "new_dest"
        jobs = [make_job(report_id="A", src_folder_name=str(d1))]
        errors = probe_destinations(jobs, mkdir=True)
        assert errors == []
        assert d1.is_dir()

    def test_mkdir_parent_missing_still_errors(self, tmp_path):
        d1 = tmp_path / "no_parent" / "child"
        jobs = [make_job(report_id="A", src_folder_name=str(d1))]
        errors = probe_destinations(jobs, mkdir=True)
        assert len(errors) == 1
        assert "存在しません" in errors[0]


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
        marker = write_completion_marker(tmp_path, 3, 1)
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
