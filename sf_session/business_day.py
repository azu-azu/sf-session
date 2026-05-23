"""営業日判定モジュール。

土日 + 日本の祝日 + extra_holidays.csv で非営業日を判定する。
"""

from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path

import jpholiday

from sf_session.config import PIPELINES_DIR

logger = logging.getLogger(__name__)

EXTRA_HOLIDAYS_FILENAME = "extra_holidays.csv"
EXTRA_HOLIDAYS_PATH = PIPELINES_DIR / EXTRA_HOLIDAYS_FILENAME


def load_extra_holidays(path: Path = EXTRA_HOLIDAYS_PATH) -> set[date]:
    """CSV (A列: YYYY-MM-DD) から追加休業日を読み込む。
    空行は無視、先頭が # のコメント行も無視。
    """
    if not path.exists():
        return set()
    holidays: set[date] = set()
    with path.open(encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or not row[0].strip():
                continue
            if row[0].lstrip().startswith("#"):
                continue
            try:
                holidays.add(date.fromisoformat(row[0].strip()))
            except ValueError:
                logger.warning("extra_holidays: skip invalid date: %s", row[0])
    return holidays


def should_run_download(
    today: date | None = None,
    extra_holidays: set[date] | None = None,
) -> tuple[bool, str]:
    """(should_run, reason) を返す。

    reason: "weekday" / "weekend" / "japanese_holiday: {name}" / "extra_holiday"
    """
    today = today or date.today()

    if today.weekday() >= 5:
        return False, "weekend"

    holiday_name = jpholiday.is_holiday_name(today)
    if holiday_name:
        return False, f"japanese_holiday: {holiday_name}"

    if extra_holidays is None:
        extra_holidays = load_extra_holidays()
    if today in extra_holidays:
        return False, "extra_holiday"

    return True, "weekday"


