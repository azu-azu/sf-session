"""sf-session 共通ユーティリティ。"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from .config import MACRO_ROOT, OUTPUT_ROOT, PROJECT_ROOT

logger = logging.getLogger(__name__)

_RE_TRAILING_DATE = re.compile(r"_(\d{8})$")

_SHORT_PATH_BASES: tuple[Path | None, ...] = (OUTPUT_ROOT, MACRO_ROOT, PROJECT_ROOT)


def short_path(path: Path | str | None) -> str:
    """ログ表示用に path を短縮する。OUTPUT_ROOT / MACRO_ROOT / PROJECT_ROOT からの relative path を返す。"""
    if path is None:
        return "-"
    p = Path(path) if isinstance(path, str) else path
    for base in _SHORT_PATH_BASES:
        if base is not None and p.is_relative_to(base):
            return str(p.relative_to(base))
    return str(p)


def _supports_hyperlink() -> bool:
    """terminal が OSC 8 hyperlink に対応しているか判定する。"""
    if not sys.stderr.isatty():
        return False
    # Windows: Windows Terminal (WT_SESSION) のみ対応。conhost はゴミ文字になる
    if os.name == "nt" and "WT_SESSION" not in os.environ:
        return False
    return True


def file_link(path: Path | str | None) -> str:
    """short_path に OSC 8 hyperlink を付与する。非対応 terminal では plain text。"""
    display = short_path(path)
    if path is None or not _supports_hyperlink():
        return display
    p = Path(path) if isinstance(path, str) else path
    try:
        uri = p.resolve().as_uri()
    except ValueError:
        return display
    return f"\033]8;;{uri}\a{display}\033]8;;\a"


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


def write_pipeline_status(
    outputs_dir: Path,
    pipeline: str,
    phase: str,
    label: str,
    *,
    clear_phases: list[str] | None = None,
) -> Path:
    """pipeline status marker を書く。同 pipeline+phase の旧ファイルは削除。

    clear_phases が指定されていれば、それらの phase のマーカーも削除する。
    """
    outputs_dir.mkdir(parents=True, exist_ok=True)
    phases_to_clear = [phase] + (clear_phases or [])
    for p in phases_to_clear:
        for old in outputs_dir.glob(f"_{pipeline}_{p}_*.txt"):
            old.unlink()
    marker = outputs_dir / f"_{pipeline}_{phase}_{label}.txt"
    marker.touch()
    logger.info("pipeline status: %s", marker.name)
    return marker


def build_output_stem(report_id: str | None, stem: str) -> str:
    """出力ファイル名の stem を組み立てる。{report_id}_{YYYYMMDD}_{stem} 形式。"""
    today = datetime.now().strftime("%Y%m%d")
    if report_id:
        return f"{report_id}_{today}_{stem}"
    return stem


def read_ids_file(path: Path) -> set[str]:
    """ID テキストファイルを読み取り、set で返す。# 行はスキップ。"""
    if not path.exists():
        raise FileNotFoundError(f"ids-file not found: {path}")
    return {
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }


def log_result_summary(
    results: Sequence,
    label: str,
    *,
    path_fn: Callable | None = None,
    show_successes: bool = False,
) -> tuple[int, int]:
    """result list のサマリーをログ出力し、(ok, ng) を返す。

    results の各要素は .success, .seq, .report_id, .elapsed, .error を持つこと。
    path_fn: path 表示文字列を返す callable。省略時は r.dest_path を使用。
    """
    ok = sum(1 for r in results if r.success)
    ng = sum(1 for r in results if not r.success)

    logger.info("*" * 50)
    logger.info("%s complete >>", label)
    logger.info("成功 %d 件 / 失敗 %d 件 / 合計 %d 件", ok, ng, len(results))

    def _path_str(r, *, link: bool = False) -> str:
        if path_fn is not None:
            return str(path_fn(r))
        dest = getattr(r, "dest_path", None)
        return file_link(dest) if link else short_path(dest)

    failures = [r for r in results if not r.success]
    if failures:
        logger.info("-" * 50)
        logger.info("失敗一覧")
        for r in failures:
            err = f" ({r.error})" if r.error else ""
            logger.info(
                "  [NG] %d件目 %s  %.1fs  %s%s",
                r.seq, r.report_id, r.elapsed, _path_str(r), err,
            )

    successes = [r for r in results if r.success]
    if show_successes and successes:
        logger.info("-" * 50)
        logger.info("成功一覧")
        for r in successes:
            logger.info("%d. %s", r.seq, _path_str(r, link=True))

    logger.info("*" * 50)
    return ok, ng
