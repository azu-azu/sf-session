"""file_collect.py のテスト。"""
from __future__ import annotations

from datetime import datetime

from sf_session.file_collect import (
    _find_csv_by_date,
    _find_csv_by_name,
)
from sf_session.utils import strip_trailing_date


class TestStripDateSuffixNonStrict:
    """strip_trailing_date(strict=False) — file_collect 用途。"""

    def test_strip(self):
        assert strip_trailing_date("01_RPT_20260313", strict=False) == "01_RPT"

    def test_no_date(self):
        assert strip_trailing_date("01_RPT", strict=False) == "01_RPT"

    def test_date_in_middle_untouched(self):
        assert strip_trailing_date("01_20260313_RPT", strict=False) == "01_20260313_RPT"

    def test_empty(self):
        assert strip_trailing_date("", strict=False) == ""


class TestFindCsvByName:
    def test_today_exact_match(self, tmp_path):
        """今日の日付サフィックスが完全一致するファイルを優先する。"""
        target = tmp_path / "01_RPT_20260319.csv"
        target.write_text("data")
        (tmp_path / "01_RPT_20260318.csv").write_text("old")
        (tmp_path / "other.csv").write_text("x")

        result = _find_csv_by_name(tmp_path, "01_RPT", "20260319")
        assert result == target

    def test_today_preferred_over_newer_mtime(self, tmp_path):
        """mtime が古くても今日の日付ファイルが優先される。"""
        import os

        today = tmp_path / "01_RPT_20260319.csv"
        today.write_text("today")
        past = datetime(2026, 3, 19, 1, 0).timestamp()
        os.utime(today, (past, past))

        yesterday = tmp_path / "01_RPT_20260318.csv"
        yesterday.write_text("yesterday")

        result = _find_csv_by_name(tmp_path, "01_RPT", "20260319")
        assert result == today

    def test_fallback_to_mtime(self, tmp_path):
        """今日の日付ファイルがなければ mtime fallback。"""
        target = tmp_path / "report_daily_20260318.csv"
        target.write_text("data")

        result = _find_csv_by_name(tmp_path, "report_daily", "20260319")
        assert result == target

    def test_not_found(self, tmp_path):
        (tmp_path / "report.csv").write_text("data")
        assert _find_csv_by_name(tmp_path, "missing", "20260319") is None

    def test_empty_folder(self, tmp_path):
        assert _find_csv_by_name(tmp_path, "any", "20260319") is None

    def test_non_csv_ignored(self, tmp_path):
        (tmp_path / "report_daily.txt").write_text("data")
        assert _find_csv_by_name(tmp_path, "report_daily", "20260319") is None

    def test_japanese_filename_fallback(self, tmp_path):
        """日本語名ファイルも mtime fallback で拾える。"""
        import os
        import time

        old_jp = tmp_path / "01_RPT_全件.csv"
        old_jp.write_text("old")
        past = datetime(2025, 12, 23).timestamp()
        os.utime(old_jp, (past, past))

        time.sleep(0.05)
        newer = tmp_path / "01_RPT_20260318.csv"
        newer.write_text("new")

        result = _find_csv_by_name(tmp_path, "01_RPT", "20260319")
        assert result == newer

    def test_with_stripped_base_picks_today(self, tmp_path):
        """呼び出し側が strip_trailing_date 済みの base を渡すケース。"""
        import os

        for i, (name, days_ago) in enumerate([
            ("01_RPT_20260313.csv", 6),
            ("01_RPT_20260316.csv", 3),
            ("01_RPT_20260319.csv", 0),
        ]):
            f = tmp_path / name
            f.write_text(f"data{i}")
            ts = datetime(2026, 3, 19 - days_ago, 9, 0).timestamp()
            os.utime(f, (ts, ts))

        base = strip_trailing_date("01_RPT_20260313", strict=False)
        result = _find_csv_by_name(tmp_path, base, "20260319")
        assert result == tmp_path / "01_RPT_20260319.csv"


class TestFindCsvByDate:
    def test_suffix_match(self, tmp_path):
        target = tmp_path / "report20260314.csv"
        target.write_text("data")

        result = _find_csv_by_date(tmp_path, "20260314")
        assert result == target

    def test_suffix_match_lowercase_ext(self, tmp_path):
        target = tmp_path / "REPORT20260314.csv"
        target.write_text("data")

        result = _find_csv_by_date(tmp_path, "20260314")
        assert result == target

    def test_mtime_fallback(self, tmp_path):
        target = tmp_path / "report.csv"
        target.write_text("data")

        today_str = datetime.now().strftime("%Y%m%d")
        result = _find_csv_by_date(tmp_path, today_str)
        assert result == target

    def test_no_match(self, tmp_path):
        import os

        (tmp_path / "old20200101.csv").write_text("data")
        past = datetime(2020, 1, 1).timestamp()
        os.utime(tmp_path / "old20200101.csv", (past, past))

        result = _find_csv_by_date(tmp_path, "20260314")
        assert result is None

    def test_picks_latest_mtime(self, tmp_path):
        import time

        today_str = datetime.now().strftime("%Y%m%d")

        (tmp_path / "a.csv").write_text("1")

        time.sleep(0.05)
        f2 = tmp_path / "b.csv"
        f2.write_text("2")

        result = _find_csv_by_date(tmp_path, today_str)
        assert result == f2
