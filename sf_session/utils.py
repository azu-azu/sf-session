"""sf-session 共通ユーティリティ。"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

_RE_TRAILING_DATE = re.compile(r"_(\d{8})$")


def setup_logging(level: str = "INFO") -> None:
    """ルートロガーを timestamped format で初期化する。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def time_label() -> str:
    """マーカーファイル用の日時ラベルを返す。"""
    now = datetime.now()
    return f"{now.month}月{now.day}日{now.hour:02d}時{now.minute:02d}分"


def format_duration(seconds: float | None) -> str:
    """秒数を「x分x秒」形式にフォーマットする。None なら '-' を返す。"""
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds:.1f}秒"
    m, s = divmod(int(seconds), 60)
    return f"{m}分{s}秒"


def strip_trailing_date(name: str, *, strict: bool = True) -> str:
    """末尾の _YYYYMMDD を除去する。

    strict=True (default): valid date かつ今年のみ strip。
    strict=False: 8桁数字なら無条件 strip。
    """
    m = _RE_TRAILING_DATE.search(name)
    if not m:
        return name
    if not strict:
        return name[: m.start()]
    try:
        dt = datetime.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        return name
    if dt.year != datetime.now().year:
        return name
    return name[: m.start()]


