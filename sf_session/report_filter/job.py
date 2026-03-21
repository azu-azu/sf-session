"""Salesforce レポートからフィルタ設定とメタデータを抽出するジョブ。

指定されたレポート ID に対して describe / run API を呼び出し、
フィルタ情報・行数・列数・オブジェクト情報を JSON で保存する。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceRefusedRequest

from ..config import PIPELINE_DIR
from .analytics_api import (
    get_object_describe_fields,
    get_report_describe,
    fetch_report_run,
)
from .annotator import _annotate_parity, _fill_custom_date_ranges
from .extractor import ExtractedFilter, extract_filters_from_report_describe
from .metadata import (
    _build_report_metadata_payload,
    _extract_column_count,
    _extract_row_count,
    _slim_object_fields,
)
from .writer import build_output_targets, initialize_output_files, write_all_outputs

logger = logging.getLogger(__name__)


def _format_elapsed(seconds: float) -> str:
    """秒数を「x分x秒」形式にフォーマットする。"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    m, s = divmod(int(seconds), 60)
    return f"{m}分{s}秒"


def _enrich_lookup_filters(
    filters: list[ExtractedFilter],
    sf: Salesforce,
    *,
    object_name: str,
    obj_describe_cache: dict[str, list[dict]],
) -> None:
    """lookup_non_sfid_value フィルタに relationship_name を付与する。"""
    for f in filters:
        assumption = str(f.assumption_used or "")
        if "lookup_non_sfid_value" not in assumption:
            continue
        column = str(f.column or "")
        if not column:
            continue

        parts = column.rsplit(".", 1)
        obj = parts[0] if len(parts) == 2 else object_name
        field_name = parts[-1]

        if not obj:
            continue

        fields = get_object_describe_fields(sf, obj, cache=obj_describe_cache)
        for finfo in fields:
            if finfo.get("name") != field_name:
                continue
            reference_to = finfo.get("referenceTo") or []
            is_poly = bool(finfo.get("polymorphicForeignKey")) or len(reference_to) > 1
            if not is_poly:
                f.relationship_name = finfo.get("relationshipName") or None
            break


def _fetch_describe(
    sf: Salesforce,
    report_id: str,
    describe_cache: dict[str, dict],
) -> tuple[dict[str, Any] | None, str | None]:
    """describe API を呼び出し (description, error_reason) を返す。"""
    try:
        return get_report_describe(sf, report_id, cache=describe_cache), None
    except SalesforceRefusedRequest as exc:
        return None, f"describe failed: {exc}"
    except TypeError as exc:
        return None, str(exc)


def _fetch_run_result(
    sf: Salesforce,
    report_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """run API を呼び出し (result, error_reason) を返す。"""
    try:
        result_raw = fetch_report_run(sf, report_id)
    except SalesforceRefusedRequest as exc:
        return None, str(exc)
    if isinstance(result_raw, dict):
        return result_raw, None
    return None, "report result is not a dict"


def _fetch_and_process_report(
    sf: Salesforce,
    report_id: str,
    index: int,
    total: int,
    report_describe_cache: dict[str, dict],
    obj_describe_cache: dict[str, list[dict]],
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    """Fetch describe + report result for one ID.

    Returns (filter_payload, metadata_payload, setup_error_reason).
    """
    t0 = time.perf_counter()

    # --- describe ---
    description, describe_error = _fetch_describe(sf, report_id, report_describe_cache)
    if describe_error is not None:
        logger.error("\n=== id: %s === (%d / %d 件)", report_id, index, total)
        logger.error("error: setup unavailable (%s)", describe_error)
        logger.info("elapsed: %s", _format_elapsed(time.perf_counter() - t0))
        return (
            {"report_id": report_id, "status": "error", "error": describe_error},
            _build_report_metadata_payload(
                report_id, description=None, report_result=None, status="error", error=describe_error,
                from_object=None, object_fields=None,
            ),
            describe_error,
        )

    extracted = extract_filters_from_report_describe(description)
    if extracted.object_name:
        _enrich_lookup_filters(
            extracted.filters,
            sf,
            object_name=extracted.object_name,
            obj_describe_cache=obj_describe_cache,
        )
    payload = extracted.to_dict()
    payload["column_count"] = _extract_column_count(description)
    payload["report_id"] = report_id
    payload["status"] = "success"

    # --- report result ---
    report_result, run_error = _fetch_run_result(sf, report_id)
    if run_error is not None:
        payload["row_count"] = None
        payload["all_data"] = None
        payload["row_count_error"] = run_error
    else:
        row_count, all_data = _extract_row_count(report_result)
        payload["row_count"] = row_count
        payload["all_data"] = all_data
        _fill_custom_date_ranges(payload, report_result)

    _annotate_parity(payload)

    from_object = extracted.object_name
    raw_obj_fields = (
        get_object_describe_fields(sf, from_object, cache=obj_describe_cache)
        if from_object else []
    )
    object_fields = _slim_object_fields(raw_obj_fields) if raw_obj_fields else None

    logger.info("\n=== id: %s === (%d / %d 件)", report_id, index, total)
    logger.info("filters: %d", len(extracted.filters))
    logger.info("column_count: %s", payload.get("column_count"))
    logger.info("row_count: %s", payload.get("row_count"))
    logger.info("elapsed: %s", _format_elapsed(time.perf_counter() - t0))

    return (
        payload,
        _build_report_metadata_payload(
            report_id, description=description, report_result=report_result, status="success",
            from_object=from_object, object_fields=object_fields,
        ),
        None,
    )


def run_report_filter_extract_job(
    sf: Salesforce,
    report_ids: list[str],
    output_path: Path = Path("report_filters.json"),
    pipeline_dir: Path = PIPELINE_DIR,
) -> dict[str, Any]:
    # --- setup ---
    output_targets = build_output_targets(output_path)
    initialize_output_files(output_targets)

    results: list[dict[str, Any]] = []
    metadata_results: list[dict[str, Any]] = []
    setup_errors: list[dict[str, str]] = []
    success_count = 0
    error_count = 0
    report_describe_cache: dict[str, dict] = {}
    obj_describe_cache: dict[str, list[dict]] = {}

    # --- fetch & process ---
    total = len(report_ids)
    for i, report_id in enumerate(report_ids, 1):
        payload, metadata_payload, setup_error_reason = _fetch_and_process_report(
            sf, report_id, i, total, report_describe_cache, obj_describe_cache
        )
        results.append(payload)
        metadata_results.append(metadata_payload)
        if setup_error_reason is not None:
            setup_errors.append({"report_id": report_id, "reason": setup_error_reason})
            error_count += 1
        else:
            success_count += 1

    # --- write & return ---
    return write_all_outputs(
        results=results,
        metadata_results=metadata_results,
        setup_errors=setup_errors,
        success_count=success_count,
        error_count=error_count,
        output_path=output_path,
        output_targets=output_targets,
        pipeline_dir=pipeline_dir,
    )
