"""macro_book_reader.py のテスト。"""
from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import patch

from sf_session.macro_book_reader import _strip_trailing_date, load_active_jobs
from sf_session.tests.helpers import make_job


class TestStripTrailingDate:
    def test_strip_current_year(self):
        year = datetime.now().year
        assert _strip_trailing_date(f"01_RPT_{year}0313") == "01_RPT"

    def test_no_date(self):
        assert _strip_trailing_date("01_RPT") == "01_RPT"

    def test_different_year_kept(self):
        assert _strip_trailing_date("01_RPT_20250313") == "01_RPT_20250313"

    def test_invalid_date_kept(self):
        assert _strip_trailing_date("01_RPT_20261332") == "01_RPT_20261332"

    def test_empty(self):
        assert _strip_trailing_date("") == ""

    def test_year_boundary(self):
        """来年の日付も strip しない。"""
        with patch("sf_session.macro_book_reader.datetime") as mock_dt:
            mock_dt.strptime = __import__("datetime").datetime.strptime
            mock_dt.now.return_value = __import__("datetime").datetime(2026, 1, 1)
            assert _strip_trailing_date("report_20270101") == "report_20270101"


class TestIdsFileEmpty:
    """ids-file が空の場合の early exit テスト。"""

    def test_ids_file_empty_returns_empty(self, tmp_path, monkeypatch, caplog):
        """ids.txt がコメントのみ → 空リスト + warning ログ。"""
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text("# コメントだけ\n# もう1行\n")

        monkeypatch.setattr(
            "sf_session.macro_book_reader.DEFAULT_IDS_FILE", ids_file,
        )
        monkeypatch.setattr(
            "sf_session.macro_book_reader.read_jobs",
            lambda *a, **kw: [make_job()],
        )

        with caplog.at_level(logging.WARNING):
            result = load_active_jobs(tmp_path, ids_file=True)

        assert result == []
        assert "0 件" in caplog.text
