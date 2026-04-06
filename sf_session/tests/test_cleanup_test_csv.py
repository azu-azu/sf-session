"""cleanup_test_csv のテスト。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sf_session.cleanup_test_csv import (
    _delete_csv_recursive,
    parse_args,
    run,
)


class TestDeleteCsvRecursive:
    def test_deletes_csv_files(self, tmp_path):
        (tmp_path / "a.csv").write_text("data")
        (tmp_path / "b.csv").write_text("data")
        (tmp_path / "keep.txt").write_text("keep")

        count = _delete_csv_recursive(tmp_path, dry_run=False)

        assert count == 2
        assert not (tmp_path / "a.csv").exists()
        assert not (tmp_path / "b.csv").exists()
        assert (tmp_path / "keep.txt").exists()

    def test_dry_run_keeps_files(self, tmp_path):
        (tmp_path / "a.csv").write_text("data")

        count = _delete_csv_recursive(tmp_path, dry_run=True)

        assert count == 1
        assert (tmp_path / "a.csv").exists()

    def test_deletes_csv_in_subdirs(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.csv").write_text("data")
        (sub / "b.csv").write_text("data")
        (sub / "keep.txt").write_text("keep")

        count = _delete_csv_recursive(tmp_path, dry_run=False)

        assert count == 2
        assert not (tmp_path / "a.csv").exists()
        assert not (sub / "b.csv").exists()
        assert (sub / "keep.txt").exists()

    def test_empty_dir(self, tmp_path):
        count = _delete_csv_recursive(tmp_path, dry_run=False)
        assert count == 0

    def test_nonexistent_dir(self, tmp_path):
        count = _delete_csv_recursive(tmp_path / "nope", dry_run=False)
        assert count == 0


class TestRunSafetyGuard:
    def test_rejects_non_devtest_pipeline(self):
        with pytest.raises(SystemExit, match="cleanup 対象外"):
            run("archive")


class TestRun:
    def _setup_csv_dir(self, tmp_path):
        csv_dir = tmp_path / "output" / "devtest" / "csv"
        csv_dir.mkdir(parents=True)
        (csv_dir / "report1.csv").write_text("data")
        (csv_dir / "report2.csv").write_text("data")
        return csv_dir

    def test_deletes_csv_dir_files(self, tmp_path):
        csv_dir = self._setup_csv_dir(tmp_path)
        macro_dir = tmp_path / "macros"
        macro_dir.mkdir()

        with patch("sf_session.cleanup_test_csv.PIPELINES") as mock_p:
            mock_cfg = mock_p.__getitem__.return_value
            mock_cfg.csv_dir = csv_dir
            mock_cfg.macro_dir = macro_dir

            total = run("devtest", dry_run=False)

        assert total == 2
        assert list(csv_dir.glob("*.csv")) == []

    def test_deletes_direct_deliver_csvs(self, tmp_path):
        csv_dir = tmp_path / "output" / "devtest" / "csv"
        csv_dir.mkdir(parents=True)

        dest = tmp_path / "direct_dest"
        dest.mkdir()
        (dest / "00O123_20260328_report.csv").write_text("data")
        (dest / "keep.txt").write_text("keep")

        macro_dir = tmp_path / "macros"
        macro_dir.mkdir()

        from sf_session.macro_book_reader import JobEntry

        fake_jobs = [
            JobEntry(
                no="1", report_id="00O123", has_filename=False,
                new_filename="", src_folder_name=str(dest),
                encode="", skip="",
            ),
        ]

        with (
            patch("sf_session.cleanup_test_csv.PIPELINES") as mock_p,
            patch("sf_session.cleanup_test_csv.read_jobs", return_value=fake_jobs),
        ):
            mock_cfg = mock_p.__getitem__.return_value
            mock_cfg.csv_dir = csv_dir
            mock_cfg.macro_dir = macro_dir

            total = run("devtest", dry_run=False)

        assert total == 1
        assert not (dest / "00O123_20260328_report.csv").exists()
        assert (dest / "keep.txt").exists()

    def test_dry_run(self, tmp_path):
        csv_dir = self._setup_csv_dir(tmp_path)
        macro_dir = tmp_path / "macros"
        macro_dir.mkdir()

        with patch("sf_session.cleanup_test_csv.PIPELINES") as mock_p:
            mock_cfg = mock_p.__getitem__.return_value
            mock_cfg.csv_dir = csv_dir
            mock_cfg.macro_dir = macro_dir

            total = run("devtest", dry_run=True)

        assert total == 2
        assert len(list(csv_dir.glob("*.csv"))) == 2  # still there


class TestParseArgs:
    def test_defaults(self):
        args = parse_args(["archive"])
        assert args.pipeline == "archive"
        assert not args.dry_run

    def test_dry_run(self):
        args = parse_args(["archive", "--dry-run"])
        assert args.dry_run
