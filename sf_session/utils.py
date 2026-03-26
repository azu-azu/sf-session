"""sf-session 共通ユーティリティ。"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


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


def read_ids_file(path: Path) -> set[str]:
    """ID テキストファイルを読み取り、set で返す。# 行はスキップ。"""
    if not path.exists():
        raise FileNotFoundError(f"ids-file not found: {path}")
    return {
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }
