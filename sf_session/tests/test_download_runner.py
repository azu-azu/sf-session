"""download_runner のテスト。"""

from __future__ import annotations

from pathlib import Path

from sf_session.download.runner import (
    export_batch,
    export_one,
)
from sf_session.tests.helpers import make_job


class TestExportOne:
    def test_empty_report_id_returns_failure(self, tmp_path):
        job = make_job(report_id=None)
        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1)
        assert not result.success
        assert "report_id が空" in result.error

    def test_timeout_returns_failure(self, tmp_path, monkeypatch):
        job = make_job()

        monkeypatch.setattr(
            "sf_session.download.runner.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.download.runner.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.download.runner.wait_for_new_download",
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
            "sf_session.download.runner.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.download.runner.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.download.runner.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1)
        assert result.success
        assert result.dest_path == downloaded

    def test_chrome_launch_failure(self, tmp_path, monkeypatch):
        job = make_job()

        monkeypatch.setattr(
            "sf_session.download.runner.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.download.runner.subprocess.Popen",
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
            "sf_session.download.runner.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.download.runner.subprocess.Popen",
            lambda cmd: launched_cmds.append(cmd),
        )
        monkeypatch.setattr(
            "sf_session.download.runner.wait_for_new_download",
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
            "sf_session.download.runner.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.download.runner.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.download.runner.wait_for_new_download",
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
            "sf_session.download.runner.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.download.runner.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.download.runner.wait_for_new_download", mock_wait
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
            "sf_session.download.runner.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.download.runner.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.download.runner.wait_for_new_download",
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
            "sf_session.download.runner.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.download.runner.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.download.runner.wait_for_new_download",
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
            "sf_session.download.runner.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "sf_session.download.runner.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "sf_session.download.runner.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        results = export_batch(
            Path("/dummy/chrome"), [job], tmp_path, interval=0
        )
        assert len(results) == 1
        assert results[0].success
        # 移動できず Downloads のまま
        assert results[0].dest_path == downloaded
