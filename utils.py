"""sf-session 共通ユーティリティ。"""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(level: str = "INFO") -> None:
    """ルートロガーを timestamped format で初期化する。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def read_ids_file(path: Path) -> set[str]:
    """ID テキストファイルを読み取り、set で返す。# 行はスキップ。"""
    if not path.exists():
        raise FileNotFoundError(f"ids-file not found: {path}")
    return {
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }
