"""パイプライン実行状態の記録と結果サマリーのログ出力。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)


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

    def _path_str(r) -> str:
        if path_fn is not None:
            return str(path_fn(r))
        dest = getattr(r, "dest_path", None)
        return str(dest) if dest is not None else "-"

    successes = [r for r in results if r.success]
    if show_successes and successes:
        logger.info("-" * 50)
        logger.info("成功一覧")
        for r in successes:
            logger.info("%d. %s", r.seq, _path_str(r))

    failures = [r for r in results if not r.success]
    if failures:
        logger.info("-" * 50)
        for r in failures:
            err = f" ({r.error})" if r.error else ""
            logger.info(
                "  [NG] %d件目 %s  %.1fs  %s%s",
                r.seq, r.report_id, r.elapsed, _path_str(r), err,
            )

    logger.info("*" * 50)
    return ok, ng
