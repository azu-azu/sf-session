"""business_day のテスト。"""

from __future__ import annotations

from datetime import date

from sf_session.business_day import should_run_download


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
