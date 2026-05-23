"""pipeline の csv_dir 直下の CSV を UTF-8 BOM に変換する。

変換先は csv_dir/utf/ サブフォルダ。

Usage:
    python -m sf_session.jis_to_utf8 archive
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import PIPELINES, VALID_PIPELINES
from .utils import setup_logging

logger = logging.getLogger(__name__)

# VBA 出力の想定エンコーディング（優先順）
_ENCODINGS = ["cp932", "utf-8-sig", "utf-8"]


def _read_bytes_as_text(path: Path) -> str:
    """候補エンコーディングで CSV を読み込み、文字列で返す。"""
    for enc in _ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, ValueError):
            continue
    raise UnicodeDecodeError(
        "multi", b"", 0, 1,
        f"どのエンコーディングでも読み込めません: {path.name}",
    )


def convert_dir(src: Path) -> Path:
    """src 直下の CSV を UTF-8 BOM に変換し、src/utf/ に出力する。"""
    dest = src / "utf"
    dest.mkdir(exist_ok=True)

    csv_files = sorted(src.glob("*.csv"))
    if not csv_files:
        logger.info("スキップ: '%s' に CSV ファイルがありません", src)
        return dest

    for csv_path in csv_files:
        text = _read_bytes_as_text(csv_path)
        out_path = dest / f"{csv_path.stem}_utf{csv_path.suffix}"
        out_path.write_text(text, encoding="utf-8-sig")

    logger.info("変換完了: %d files → '%s'", len(csv_files), dest)
    return dest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="csv_dir 直下の CSV を UTF-8 BOM に変換する",
    )
    parser.add_argument(
        "pipeline",
        choices=VALID_PIPELINES,
        help="実行対象の pipeline 名",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    pipeline = PIPELINES[args.pipeline]

    if not pipeline.csv_dir.is_dir():
        logger.error("'%s' が見つかりません。", pipeline.csv_dir)
        return 1

    convert_dir(pipeline.csv_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
