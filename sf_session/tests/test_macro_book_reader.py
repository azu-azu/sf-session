"""macro_book_reader.py のテスト。"""
from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import patch

from sf_session.config import PipelineConfig
from sf_session.macro_book_reader import load_active_jobs
from sf_session.utils import strip_trailing_date
from sf_session.tests.helpers import make_job


class TestStripTrailingDate:
    def test_strip_current_year(self):
        year = datetime.now().year
        assert strip_trailing_date(f"01_RPT_{year}0313") == "01_RPT"

    def test_no_date(self):
        assert strip_trailing_date("01_RPT") == "01_RPT"

    def test_different_year_kept(self):
        assert strip_trailing_date("01_RPT_20250313") == "01_RPT_20250313"

    def test_invalid_date_kept(self):
        assert strip_trailing_date("01_RPT_20261332") == "01_RPT_20261332"

    def test_empty(self):
        assert strip_trailing_date("") == ""

    def test_year_boundary(self):
        """来年の日付も strip しない。"""
        with patch("sf_session.utils.datetime") as mock_dt:
            mock_dt.strptime = __import__("datetime").datetime.strptime
            mock_dt.now.return_value = __import__("datetime").datetime(2026, 1, 1)
            assert strip_trailing_date("report_20270101") == "report_20270101"


class TestIdsFileEmpty:
    """ids-file が空の場合の early exit テスト。"""

    def test_ids_file_empty_returns_empty(self, tmp_path, monkeypatch, caplog):
        """ids.txt がコメントのみ → 空リスト + warning ログ。"""
        # PIPELINES_DIR を tmp_path に向ける → pipeline.ids_file が tmp_path 配下になる
        monkeypatch.setattr("sf_session.config.PIPELINES_DIR", tmp_path)

        pipeline = PipelineConfig(name="test", macro_dir=tmp_path)
        # pipeline.ids_file = tmp_path / "test" / "ids_file" / "ids.txt"
        ids_file = pipeline.ids_file
        ids_file.parent.mkdir(parents=True)
        ids_file.write_text("# コメントだけ\n# もう1行\n")

        monkeypatch.setattr(
            "sf_session.macro_book_reader.read_jobs",
            lambda *a, **kw: [make_job()],
        )

        with caplog.at_level(logging.WARNING):
            result = load_active_jobs(pipeline, ids_file=True)

        assert result == []
        assert "0 件" in caplog.text
