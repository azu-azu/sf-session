"""business_day のテスト。"""

from __future__ import annotations

from datetime import date

from sf_session.business_day import is_business_day, should_run_download


class TestIsBusinessDay:
    def test_weekday(self):
        # 2026-03-23 = Monday
        assert is_business_day(date(2026, 3, 23)) is True

    def test_saturday(self):
        assert is_business_day(date(2026, 3, 21)) is False

    def test_sunday(self):
        assert is_business_day(date(2026, 3, 22)) is False

    def test_national_holiday(self):
        # 2026-01-01 = 元日 (Thursday)
        assert is_business_day(date(2026, 1, 1)) is False

    def test_substitute_holiday(self):
        # 振替休日: 2026-05-06 (水) ← 5/5 こどもの日が火曜なので振替ではない
        # 確実な振替休日: 2023-01-02 (月) ← 1/1 元日が日曜
        assert is_business_day(date(2023, 1, 2)) is False


class TestShouldRunDownload:
    def test_weekday(self):
        ok, reason = should_run_download(date(2026, 3, 24))
        assert ok is True
        assert reason == "weekday"

    def test_weekend(self):
        ok, reason = should_run_download(date(2026, 3, 21))
        assert ok is False
        assert reason == "weekend"

    def test_holiday(self):
        ok, reason = should_run_download(date(2026, 1, 1))
        assert ok is False
        assert "japanese_holiday" in reason
        assert "元日" in reason
