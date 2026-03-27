"""business_day のテスト。"""

from __future__ import annotations

from datetime import date

from sf_session.business_day import load_extra_holidays, should_run_download


class TestShouldRunDownload:
    def test_weekday(self):
        ok, reason = should_run_download(date(2026, 3, 24))
        assert ok is True
        assert reason == "weekday"

    def test_monday(self):
        # 2026-03-23 = Monday
        ok, _ = should_run_download(date(2026, 3, 23))
        assert ok is True

    def test_saturday(self):
        ok, reason = should_run_download(date(2026, 3, 21))
        assert ok is False
        assert reason == "weekend"

    def test_sunday(self):
        ok, reason = should_run_download(date(2026, 3, 22))
        assert ok is False
        assert reason == "weekend"

    def test_national_holiday(self):
        # 2026-01-01 = 元日 (Thursday)
        ok, reason = should_run_download(date(2026, 1, 1))
        assert ok is False
        assert "japanese_holiday" in reason
        assert "元日" in reason

    def test_substitute_holiday(self):
        # 振替休日: 2023-01-02 (月) ← 1/1 元日が日曜
        ok, reason = should_run_download(date(2023, 1, 2))
        assert ok is False

    def test_extra_holiday(self):
        extras = {date(2026, 12, 31)}
        ok, reason = should_run_download(date(2026, 12, 31), extra_holidays=extras)
        assert ok is False
        assert reason == "extra_holiday"

    def test_extra_holiday_not_matched(self):
        extras = {date(2026, 12, 31)}
        ok, reason = should_run_download(date(2026, 3, 24), extra_holidays=extras)
        assert ok is True

    def test_extra_holidays_empty_set(self):
        ok, reason = should_run_download(date(2026, 3, 24), extra_holidays=set())
        assert ok is True
        assert reason == "weekday"


class TestLoadExtraHolidays:
    def test_file_not_found(self, tmp_path):
        result = load_extra_holidays(tmp_path / "nonexistent.csv")
        assert result == set()

    def test_load_dates(self, tmp_path):
        csv_file = tmp_path / "holidays.csv"
        csv_file.write_text("2026-12-31\n2027-01-02\n")
        result = load_extra_holidays(csv_file)
        assert result == {date(2026, 12, 31), date(2027, 1, 2)}

    def test_skip_empty_lines(self, tmp_path):
        csv_file = tmp_path / "holidays.csv"
        csv_file.write_text("2026-12-31\n\n2027-01-02\n")
        result = load_extra_holidays(csv_file)
        assert len(result) == 2

    def test_skip_invalid_date(self, tmp_path):
        csv_file = tmp_path / "holidays.csv"
        csv_file.write_text("2026-12-31\nnot-a-date\n")
        result = load_extra_holidays(csv_file)
        assert result == {date(2026, 12, 31)}
