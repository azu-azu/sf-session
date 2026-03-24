"""営業日判定モジュール。

土日 + 日本の祝日で非営業日を判定する。
"""

from __future__ import annotations

from datetime import date

import jpholiday


def should_run_download(today: date | None = None) -> tuple[bool, str]:
    """(should_run, reason) を返す。

    reason: "weekday" / "weekend" / "japanese_holiday: {name}"
    """
    today = today or date.today()

    if today.weekday() >= 5:
        return False, "weekend"

    holiday_name = jpholiday.is_holiday_name(today)
    if holiday_name:
        return False, f"japanese_holiday: {holiday_name}"

    return True, "weekday"


def is_business_day(today: date | None = None) -> bool:
    """today が営業日かどうかを返す。"""
    ok, _ = should_run_download(today)
    return ok
