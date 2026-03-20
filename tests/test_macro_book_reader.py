"""macro_book_reader.py のテスト。"""
from __future__ import annotations

from unittest.mock import patch

from sf_session.macro_book_reader import _strip_trailing_date


class TestStripTrailingDate:
    def test_strip_current_year(self):
        assert _strip_trailing_date("01_RPT_20260313") == "01_RPT"

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
