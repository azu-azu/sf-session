"""report_filter のファイル出力責務を担う writer モジュール。

Output:
    outputs_log/report_filters/  -- フィルタ抽出結果 (JSON + ID リスト)
    outputs_log/errors/          -- setup エラーログ
    pipelines/{report_id}/       -- report_metadata.json
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..config import OUTPUT_ERRORS_DIR
from .annotator import _split_auto_manual
from .metadata import _as_non_empty_str

logger = logging.getLogger(__name__)


def _deduplicate_ids(ids: Iterable[str]) -> list[str]:
    """順序を保ちつつ重複を除去する。"""
    return list(dict.fromkeys(ids))


def build_output_targets(output_path: Path) -> dict[str, Path]:
    stem = output_path.stem
    suffix = output_path.suffix or ".json"
    return {
        "all_json": output_path,
        "metadata_json": output_path.with_name(f"{stem}_metadata{suffix}"),
        "setup_error_log": OUTPUT_ERRORS_DIR / "report_setup_errors.log",
        "auto_json": output_path.with_name(f"{stem}_auto{suffix}"),
        "manual_json": output_path.with_name(f"{stem}_manual{suffix}"),
        "auto_ids": output_path.with_name("report_ids_auto.txt"),
        "manual_ids": output_path.with_name("report_ids_manual.txt"),
    }


def initialize_output_files(targets: dict[str, Path]) -> None:
    json_keys = ("all_json", "metadata_json", "auto_json", "manual_json")
    text_keys = ("auto_ids", "manual_ids", "setup_error_log")

    for key in json_keys:
        path = targets[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")

    for key in text_keys:
        path = targets[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


def _write_setup_error_log(path: Path, items: list[dict[str, str]]) -> None:
    lines: list[str] = []
    for item in items:
        report_id = str(item.get("report_id") or "-")
        reason = str(item.get("reason") or "-")
        lines.append(f"{report_id}\t{reason}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_pipeline_metadata_files(metadata_results: list[dict[str, Any]], pipeline_dir: Path) -> None:
    for item in metadata_results:
        report_id = _as_non_empty_str(item.get("report_id"))
        if not report_id:
            continue
        target_dir = (pipeline_dir / report_id).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "report_metadata.json"
        target_path.write_text(
            json.dumps(item, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def write_all_outputs(
    *,
    results: list[dict[str, Any]],
    metadata_results: list[dict[str, Any]],
    setup_errors: list[dict[str, str]],
    success_count: int,
    error_count: int,
    output_path: Path,
    output_targets: dict[str, Path],
    pipeline_dir: Path,
) -> dict[str, Any]:
    metadata_json_path = output_targets["metadata_json"]
    setup_error_log_path = output_targets["setup_error_log"]
    auto_json_path = output_targets["auto_json"]
    manual_json_path = output_targets["manual_json"]
    auto_ids_path = output_targets["auto_ids"]
    manual_ids_path = output_targets["manual_ids"]

    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_json_path.write_text(json.dumps(metadata_results, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_setup_error_log(setup_error_log_path, setup_errors)
    _write_pipeline_metadata_files(metadata_results, pipeline_dir)

    auto_results, manual_results = _split_auto_manual(results)
    auto_ids = _deduplicate_ids(str(r["report_id"]) for r in auto_results if r.get("report_id"))
    manual_ids = _deduplicate_ids(str(r["report_id"]) for r in manual_results if r.get("report_id"))

    auto_json_path.write_text(json.dumps(auto_results, ensure_ascii=False, indent=2), encoding="utf-8")
    manual_json_path.write_text(json.dumps(manual_results, ensure_ascii=False, indent=2), encoding="utf-8")
    auto_ids_path.write_text("\n".join(auto_ids), encoding="utf-8")
    manual_ids_path.write_text("\n".join(manual_ids), encoding="utf-8")

    logger.info("*" * 50)
    logger.info("auto=%d manual=%d", len(auto_results), len(manual_results))
    logger.info("filter-extract complete: %s extracted, %s errors (non-fatal).", success_count, error_count)
    logger.info("*" * 50)
    logger.info("Filter extraction file written: %s", output_path)
    logger.info("Metadata JSON written: %s", metadata_json_path)
    logger.info("Setup error log written: %s", setup_error_log_path)
    logger.info("Auto JSON written: %s", auto_json_path)
    logger.info("Manual JSON written: %s", manual_json_path)
    logger.info("Auto IDs written: %s", auto_ids_path)
    logger.info("Manual IDs written: %s", manual_ids_path)

    return {
        "success_count": success_count,
        "error_count": error_count,
        "auto_count": len(auto_results),
        "manual_count": len(manual_results),
        "all_json_path": output_path.resolve(),
        "metadata_json_path": metadata_json_path.resolve(),
        "setup_error_log_path": setup_error_log_path.resolve(),
        "auto_json_path": auto_json_path.resolve(),
        "manual_json_path": manual_json_path.resolve(),
        "auto_ids_path": auto_ids_path.resolve(),
        "manual_ids_path": manual_ids_path.resolve(),
    }
