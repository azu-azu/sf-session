"""dl_batch のテスト。"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from sf_session.config import CHROME_EXE_PATH, CHROME_USER_DATA_DIR
from sf_session.dl_batch import (
    DEFAULT_POLL,
    DEFAULT_TIMEOUT,
    DEFAULT_INTERVAL,
    ExportResult,
    build_destination,
    export_batch,
    export_one,
    log_summary,
    parse_args,
    write_success_ids,
)
from sf_session.browser import REMOTE_DEBUGGING_PORT

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

        with patch("sf_session.dl_batch.datetime") as mock_dt:
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

        with patch("sf_session.dl_batch.datetime") as mock_dt:
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

        with patch("sf_session.dl_batch.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260318"
            result = build_destination(
                job, downloaded, date_suffix=True, output_dir=out_dir,
            )

        assert result == out_dir / "00O999_report_20260318.csv"


class TestExportOne:
    def test_empty_report_id_returns_failure(self, tmp_path):
        job = make_job(report_id=None)
        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1)
        assert not result.success
        assert "report_id が空" in result.error

    def test_timeout_returns_failure(self, tmp_path, monkeypatch):
        job = make_job()

        monkeypatch.setattr(
            "sf_session.dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.wait_for_new_download",
            lambda *a, **kw: (_ for _ in ()).throw(
                TimeoutError("timeout")
            ),
        )

        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1, timeout=1)
        assert not result.success
        assert "timeout" in result.error

    def test_success(self, tmp_path, monkeypatch):
        job = make_job()
        downloaded = tmp_path / "report.csv"
        downloaded.write_text("data")

        monkeypatch.setattr(
            "sf_session.dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1)
        assert result.success
        assert result.dest_path == downloaded

    def test_chrome_launch_failure(self, tmp_path, monkeypatch):
        job = make_job()

        monkeypatch.setattr(
            "sf_session.dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.subprocess.Popen",
            lambda cmd: (_ for _ in ()).throw(OSError("not found")),
        )

        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1)
        assert not result.success
        assert "Chrome 起動失敗" in result.error

    def test_user_data_dir_passed_to_chrome(self, tmp_path, monkeypatch):
        job = make_job()
        downloaded = tmp_path / "report.csv"
        downloaded.write_text("data")

        launched_cmds: list[list[str]] = []
        monkeypatch.setattr(
            "sf_session.dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.subprocess.Popen",
            lambda cmd: launched_cmds.append(cmd),
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        udd = tmp_path / "ChromeProfile"
        result = export_one(
            Path("/dummy/chrome"), job, tmp_path,
            seq=1, user_data_dir=udd, profile_directory="Profile 1",
        )
        assert result.success
        cmd = launched_cmds[0]
        assert f"--user-data-dir={udd}" in cmd
        assert "--profile-directory=Profile 1" in cmd


class TestExportBatch:
    def test_skip_filtered_by_caller(self, tmp_path, monkeypatch):
        """skip フィルタは呼び出し側の責務。active_jobs のみ渡す。"""
        all_jobs = [
            make_job(no="1", skip="x"),
            make_job(no="2", skip=""),
        ]
        active_jobs = [j for j in all_jobs if not j.skip]

        downloaded = tmp_path / "report.csv"
        downloaded.write_text("data")

        monkeypatch.setattr(
            "sf_session.dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        results = export_batch(
            Path("/dummy/chrome"), active_jobs, tmp_path, interval=0
        )
        assert len(results) == 1
        assert results[0].seq == 1

    def test_failure_continues(self, tmp_path, monkeypatch):
        """1件目が失敗しても2件目は実行される。"""
        call_count = {"n": 0}

        def mock_wait(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise TimeoutError("timeout")
            downloaded = tmp_path / "report2.csv"
            downloaded.write_text("data2")
            return downloaded

        jobs = [
            make_job(no="1"),
            make_job(no="2"),
        ]

        monkeypatch.setattr(
            "sf_session.dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.wait_for_new_download", mock_wait
        )

        results = export_batch(
            Path("/dummy/chrome"), jobs, tmp_path, interval=0
        )
        assert len(results) == 2
        assert not results[0].success
        assert results[1].success

    def test_move_to_dest_dir(self, tmp_path, monkeypatch):
        """成功時にファイルが dest_dir に移動される。"""
        dest_dir = tmp_path / "output"
        dest_dir.mkdir()

        downloaded = tmp_path / "dl" / "report.csv"
        downloaded.parent.mkdir()
        downloaded.write_text("data")

        job = make_job(no="1", src_folder_name=str(dest_dir))

        monkeypatch.setattr(
            "sf_session.dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        results = export_batch(
            Path("/dummy/chrome"), [job], tmp_path / "dl", interval=0
        )
        assert len(results) == 1
        assert results[0].success
        assert results[0].dest_path == dest_dir / "report.csv"
        assert (dest_dir / "report.csv").exists()

    def test_output_dir_moves_files(self, tmp_path, monkeypatch):
        """output_dir 指定時、output_dir に report_id prefix で移動。"""
        out_dir = tmp_path / "outputs_csv"
        out_dir.mkdir()

        downloaded = tmp_path / "dl" / "report.csv"
        downloaded.parent.mkdir()
        downloaded.write_text("data")

        job = make_job(no="1", report_id="00O999")

        monkeypatch.setattr(
            "sf_session.dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        results = export_batch(
            Path("/dummy/chrome"), [job], tmp_path / "dl",
            interval=0, output_dir=out_dir,
        )
        assert len(results) == 1
        assert results[0].success
        assert results[0].dest_path == out_dir / "00O999_report.csv"
        assert (out_dir / "00O999_report.csv").exists()

    def test_dest_dir_missing_stays_in_downloads(self, tmp_path, monkeypatch):
        """移動先フォルダが存在しない場合、Downloads に残る。"""
        downloaded = tmp_path / "report.csv"
        downloaded.write_text("data")

        job = make_job(
            no="1", src_folder_name=str(tmp_path / "nonexistent")
        )

        monkeypatch.setattr(
            "sf_session.dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        results = export_batch(
            Path("/dummy/chrome"), [job], tmp_path, interval=0
        )
        assert len(results) == 1
        assert results[0].success
        # 移動できず Downloads のまま
        assert results[0].dest_path == downloaded


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


class TestParseArgs:
    def test_override_chrome_path(self):
        args = parse_args(["--chrome-path", "/usr/bin/chrome"])
        assert args.chrome_path == "/usr/bin/chrome"

    def test_default_chrome_path(self):
        args = parse_args([])
        assert args.chrome_path == CHROME_EXE_PATH

    def test_defaults(self):
        args = parse_args([])
        assert args.timeout == DEFAULT_TIMEOUT
        assert args.poll == DEFAULT_POLL
        assert args.interval == DEFAULT_INTERVAL
        assert not args.date_suffix
        assert not args.dry_run
        assert not args.direct_deliver
        assert not args.my_chrome
        assert not args.ids_file
        assert args.user_data_dir == CHROME_USER_DATA_DIR
        assert args.profile_directory is None
        assert args.port == REMOTE_DEBUGGING_PORT
        assert not args.no_login_check

    def test_all_flags(self):
        args = parse_args([
            "--chrome-path", "chrome",
            "--download-dir", "/tmp/dl",
            "--timeout", "30",
            "--poll", "0.5",
            "--date-suffix",
            "--interval", "5.0",
            "--direct-deliver",
            "--ids-file",
            "--dry-run",
            "--my-chrome",
            "--user-data-dir", CHROME_USER_DATA_DIR,
            "--profile-directory", "Profile 1",
            "--port", "9333",
            "--no-login-check",
        ])
        assert args.download_dir == "/tmp/dl"
        assert args.timeout == 30
        assert args.poll == 0.5
        assert args.date_suffix
        assert args.interval == 5.0
        assert args.direct_deliver
        assert args.ids_file
        assert args.dry_run
        assert args.my_chrome
        assert args.user_data_dir == CHROME_USER_DATA_DIR
        assert args.profile_directory == "Profile 1"
        assert args.port == 9333
        assert args.no_login_check


class TestWriteSuccessIds:
    def test_writes_success_ids(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sf_session.dl_batch.OUTPUT_RESULTS_DIR", tmp_path)
        results = [
            ExportResult(seq=1, report_id="00O001", success=True, elapsed=1.0),
            ExportResult(seq=2, report_id="00O002", success=False, elapsed=2.0),
            ExportResult(seq=3, report_id="00O003", success=True, elapsed=1.5),
        ]

        with patch("sf_session.dl_batch.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260321"
            path = write_success_ids(results)

        assert path == tmp_path / "success_ids_20260321.txt"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert lines == ["00O001", "00O003"]

    def test_no_success_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sf_session.dl_batch.OUTPUT_RESULTS_DIR", tmp_path)
        results = [
            ExportResult(seq=1, report_id="00O001", success=False, elapsed=1.0),
        ]
        assert write_success_ids(results) is None

    def test_creates_dir_if_missing(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "outputs_result"
        monkeypatch.setattr("sf_session.dl_batch.OUTPUT_RESULTS_DIR", out_dir)
        results = [
            ExportResult(seq=1, report_id="00O001", success=True, elapsed=1.0),
        ]

        with patch("sf_session.dl_batch.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260321"
            path = write_success_ids(results)

        assert out_dir.is_dir()
        assert path is not None
        assert path.exists()
