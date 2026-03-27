"""file_deliver のテスト。"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from sf_session.download.outputs import build_destination
from sf_session.file_deliver import (
    DistributeResult,
    build_job_lookup,
    distribute_files,
    log_summary,
    main,
    match_file_to_job,
    parse_args,
)
from sf_session.tests.helpers import make_job


class TestBuildJobLookup:
    def test_builds_lookup(self):
        jobs = [make_job(report_id="AAA"), make_job(report_id="BBB")]
        lookup = build_job_lookup(jobs)
        assert set(lookup.keys()) == {"AAA", "BBB"}

    def test_skips_none_report_id(self):
        jobs = [make_job(report_id=None), make_job(report_id="BBB")]
        lookup = build_job_lookup(jobs)
        assert set(lookup.keys()) == {"BBB"}


class TestMatchFileToJob:
    def test_match(self):
        lookup = build_job_lookup([make_job(report_id="00O123")])
        job = match_file_to_job("00O123_report.csv", lookup)
        assert job is not None
        assert job.report_id == "00O123"

    def test_no_match(self):
        lookup = build_job_lookup([make_job(report_id="00O123")])
        assert match_file_to_job("00OOTHER_report.csv", lookup) is None

    def test_partial_id_no_match(self):
        lookup = build_job_lookup([make_job(report_id="00O123")])
        assert match_file_to_job("00O12_report.csv", lookup) is None

    def test_requires_underscore_separator(self):
        lookup = build_job_lookup([make_job(report_id="00O123")])
        assert match_file_to_job("00O123report.csv", lookup) is None


class TestBuildDestination:
    def test_no_filename(self, tmp_path):
        job = make_job(report_id="00O123", src_folder_name=str(tmp_path))
        source = tmp_path / "00O123_report.csv"
        source.touch()

        with patch("sf_session.utils.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, source)

        assert result == tmp_path / "00O123_20260327_00O123_report.csv"

    def test_with_new_filename(self, tmp_path):
        job = make_job(
            report_id="00O123",
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="daily_export",
        )
        source = tmp_path / "00O123_original.csv"
        source.touch()

        with patch("sf_session.utils.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, source)

        assert result == tmp_path / "00O123_20260327_daily_export.csv"

    def test_preserves_extension(self, tmp_path):
        job = make_job(
            report_id="00O123",
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="output",
        )
        source = tmp_path / "00O123_data.xls"
        source.touch()

        with patch("sf_session.utils.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            result = build_destination(job, source)

        assert result == tmp_path / "00O123_20260327_output.xls"

    def test_no_report_id(self, tmp_path):
        """report_id が空なら prefix なし。"""
        job = make_job(report_id="", src_folder_name=str(tmp_path))
        source = tmp_path / "some_report.csv"
        source.touch()

        result = build_destination(job, source)
        assert result == tmp_path / "some_report.csv"


class TestDistributeFiles:
    def test_moves_file_to_dest(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        f = src_dir / "00O123_report.csv"
        f.write_text("data")

        jobs = [make_job(report_id="00O123", src_folder_name=str(dest_dir))]

        with patch("sf_session.utils.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            results = distribute_files(src_dir, jobs)

        assert len(results) == 1
        assert results[0].success
        expected = dest_dir / "00O123_20260327_00O123_report.csv"
        assert results[0].dest_path == expected
        assert expected.exists()
        assert f.exists()  # コピーなので元ファイルは残る

    def test_renames_file(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        f = src_dir / "00O123_original.csv"
        f.write_text("data")

        jobs = [make_job(
            report_id="00O123",
            src_folder_name=str(dest_dir),
            has_filename=True,
            new_filename="renamed",
        )]

        with patch("sf_session.utils.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            results = distribute_files(src_dir, jobs)

        assert len(results) == 1
        assert results[0].success
        expected = dest_dir / "00O123_20260327_renamed.csv"
        assert results[0].dest_path == expected
        assert expected.exists()

    def test_dest_dir_missing(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()

        f = src_dir / "00O123_report.csv"
        f.write_text("data")

        jobs = [make_job(
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

        jobs = [make_job(report_id="00O123")]
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
            make_job(no="1", report_id="00OAAA", src_folder_name=str(dest1)),
            make_job(no="2", report_id="00OBBB", src_folder_name=str(dest2)),
        ]

        with patch("sf_session.utils.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260327"
            results = distribute_files(src_dir, jobs)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert (dest1 / "00OAAA_20260327_00OAAA_report_a.csv").exists()
        assert (dest2 / "00OBBB_20260327_00OBBB_report_b.csv").exists()

    def test_directories_ignored(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "00O123_subdir").mkdir()

        jobs = [make_job(report_id="00O123")]
        results = distribute_files(src_dir, jobs)
        assert len(results) == 0


class TestLogSummary:
    def test_all_success(self, caplog):
        results = [
            DistributeResult(
                seq=1, report_id="00O1",
                success=True, elapsed=1.5, dest_path=Path("/out/r.csv"),
            ),
        ]
        with caplog.at_level(logging.INFO):
            log_summary(results)
        assert "成功 1 件" in caplog.text
        assert "[NG]" not in caplog.text
        assert "-" * 50 not in caplog.text

    def test_with_failures(self, caplog):
        results = [
            DistributeResult(
                seq=1, report_id="00O1",
                success=True, elapsed=1.5, dest_path=Path("/out/r.csv"),
            ),
            DistributeResult(
                seq=2, report_id="00O2",
                success=False, error="振り分け先フォルダが存在しません",
            ),
        ]
        with caplog.at_level(logging.INFO):
            log_summary(results)
        assert "成功 1 件" in caplog.text
        assert "失敗 1 件" in caplog.text
        assert "[NG] 2件目 00O2" in caplog.text
        assert "00O1" not in caplog.text.split("[NG]")[0].split("成功")[1]


class TestMainProbeFailure:
    def test_returns_1_when_probe_fails(self, tmp_path, monkeypatch):
        """移動先フォルダが存在しない場合、main() が 1 を返す。"""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "dummy.csv").write_text("data")

        jobs = [make_job(
            report_id="00O123",
            src_folder_name=str(tmp_path / "nonexistent"),
        )]

        monkeypatch.setattr(
            "sf_session.file_deliver.load_active_jobs", lambda *a, **kw: jobs,
        )
        rc = main(["archive", "--source-dir", str(source_dir)])
        assert rc == 1


class TestMainMkdirFlag:
    def test_mkdir_creates_dest_and_succeeds(self, tmp_path, monkeypatch):
        """--mkdir 付きで移動先が存在しない場合、親があれば自動作成して probe 通過。"""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "00O123_report.csv").write_text("data")

        dest_dir = tmp_path / "new_dest"
        jobs = [make_job(
            report_id="00O123",
            src_folder_name=str(dest_dir),
        )]

        monkeypatch.setattr(
            "sf_session.file_deliver.load_active_jobs", lambda *a, **kw: jobs,
        )
        rc = main(["archive", "--source-dir", str(source_dir), "--mkdir"])
        assert dest_dir.is_dir()
        assert rc == 0

    def test_mkdir_parent_missing_returns_1(self, tmp_path, monkeypatch):
        """--mkdir でも親フォルダがなければ従来通り error。"""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "00O123_report.csv").write_text("data")

        dest_dir = tmp_path / "no_parent" / "child"
        jobs = [make_job(
            report_id="00O123",
            src_folder_name=str(dest_dir),
        )]

        monkeypatch.setattr(
            "sf_session.file_deliver.load_active_jobs", lambda *a, **kw: jobs,
        )
        rc = main(["archive", "--source-dir", str(source_dir), "--mkdir"])
        assert rc == 1


class TestParseArgs:
    def test_defaults(self):
        args = parse_args(["archive"])
        assert args.pipeline == "archive"
        assert not args.dry_run
        assert not args.ids_file
        assert not args.mkdir
        assert args.macro_dir is None
        assert args.source_dir is None

    def test_mkdir_flag(self):
        args = parse_args(["archive", "--mkdir"])
        assert args.mkdir

    def test_all_flags(self):
        args = parse_args([
            "archive",
            "--ids-file",
            "--dry-run",
            "--macro-dir", "/tmp/macro",
        ])
        assert args.ids_file
        assert args.dry_run
        assert args.macro_dir == Path("/tmp/macro")

    def test_missing_pipeline_exits(self):
        with pytest.raises(SystemExit):
            parse_args([])

    def test_unknown_pipeline_exits(self):
        with pytest.raises(SystemExit):
            parse_args(["unknown"])
