"""sf-session 共通ユーティリティ。"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_RE_TRAILING_DATE = re.compile(r"_(\d{8})$")


def setup_logging(level: str = "INFO") -> None:
    """ルートロガーを timestamped format で初期化する。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def find_latest_success_ids(results_dir: Path) -> Path | None:
    """results_dir から最新の success_ids_*.txt を返す。"""
    if not results_dir.is_dir():
        return None
    candidates = sorted(results_dir.glob("success_ids_*.txt"))
    return candidates[-1] if candidates else None


def time_label() -> str:
    """マーカーファイル用の日時ラベルを返す。"""
    now = datetime.now()
    return f"{now.month}月{now.day}日{now.hour}時{now.minute}分"


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


def write_pipeline_status(
    outputs_dir: Path, pipeline: str, phase: str, label: str,
) -> Path:
    """outputs/ 直下に pipeline status marker を書く。同 pipeline+phase の旧ファイルは削除。"""
    outputs_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{pipeline}_{phase}_"
    for old in outputs_dir.glob(f"{prefix}*.txt"):
        old.unlink()
    marker = outputs_dir / f"{prefix}{label}.txt"
    marker.touch()
    logger.info("pipeline status: %s", marker.name)
    return marker


def read_ids_file(path: Path) -> set[str]:
    """ID テキストファイルを読み取り、set で返す。# 行はスキップ。"""
    if not path.exists():
        raise FileNotFoundError(f"ids-file not found: {path}")
    return {
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }
