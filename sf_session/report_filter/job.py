"""Salesforce レポートの probe job orchestrator.

指定されたレポート ID に対して describe / run API を呼び出し、
レポート名・列数・行数を取得して Excel に書き出す。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceRefusedRequest

from ..config import SF_BASE_URL
from .analytics_api import (
    fetch_report_run,
    get_column_label,
    get_report_describe,
    parse_detail_meta,
)
from .job_result import JobResult, make_result
from .result_exporter import write_result_excel
from .result_exporter import _format_duration

logger = logging.getLogger(__name__)

_NETWORK_ERRORS = (RequestsTimeout, RequestsConnectionError)


def _extract_row_count(report_result: dict[str, Any]) -> int | None:
    """factMap から最大行数を取り出す。"""
    fact_map = report_result.get("factMap")
    if not isinstance(fact_map, dict):
        return None

    max_rows = 0
    has_any = False
    for value in fact_map.values():
        if not isinstance(value, dict):
            continue
        rows = value.get("rows")
        if isinstance(rows, list):
            has_any = True
            max_rows = max(max_rows, len(rows))

    return max_rows if has_any else 0


def _probe_single_report(
    sf: Salesforce,
    report_id: str,
    index: int,
    total: int,
    describe_cache: dict[str, dict],
) -> JobResult:
    """1 レポートの describe + run を実行して JobResult を返す。"""
    result = make_result(job_id=report_id)
    result.report_id = report_id
    result.report_url = f"{SF_BASE_URL}/{report_id}"

    # --- describe ---
    try:
        description = get_report_describe(sf, report_id, cache=describe_cache)
    except (SalesforceRefusedRequest, TypeError, *_NETWORK_ERRORS) as exc:
        logger.error(
            "  [%d/%d] %s — describe failed: %s", index, total, report_id, exc
        )
        result.status = "failed"
        result.finish(error=f"describe failed: {exc}")
        return result

    # report name
    report_meta = description.get("reportMetadata") or {}
    result.report_name = report_meta.get("name") or None

    # columns
    detail_columns, col_info = parse_detail_meta(description)
    columns = [get_column_label(col_info, c) for c in detail_columns]
    column_count = len(detail_columns)

    # --- run ---
    try:
        run_result = fetch_report_run(sf, report_id)
    except (SalesforceRefusedRequest, *_NETWORK_ERRORS) as exc:
        logger.error(
            "  [%d/%d] %s — run failed: %s", index, total, report_id, exc
        )
        result.status = "failed"
        result.finish(
            column_count=column_count,
            discovery_columns=columns,
            error=f"run failed: {exc}",
        )
        return result

    if not isinstance(run_result, dict):
        result.status = "failed"
        result.finish(
            column_count=column_count,
            discovery_columns=columns,
            error="report result is not a dict",
        )
        return result

    row_count = _extract_row_count(run_result)

    result.status = "probed"
    result.finish(
        row_count=row_count,
        column_count=column_count,
        discovery_columns=columns,
    )

    logger.info(
        "  [%d/%d] %s — name=%s, cols=%d, rows=%s, %s",
        index,
        total,
        report_id,
        result.report_name,
        column_count,
        row_count,
        _format_duration(result.duration_seconds),
    )
    return result


def run_report_probe_job(
    sf: Salesforce,
    report_ids: list[str],
    output_path: Path | None = None,
) -> Path:
    """全 report_ids を probe して Excel に書き出す。

    Returns: 出力した Excel ファイルの絶対パス。
    """
    total = len(report_ids)
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("Probe start: %d reports", total)

    describe_cache: dict[str, dict] = {}
    results: list[JobResult] = []

    for i, report_id in enumerate(report_ids, 1):
        result = _probe_single_report(
            sf, report_id, i, total, describe_cache
        )
        results.append(result)

    excel_path = write_result_excel(results, output_path=output_path, run_ts=run_ts)

    success = sum(1 for r in results if r.status != "failed")
    failed = sum(1 for r in results if r.status == "failed")
    logger.info(
        "Probe complete: %d success, %d failed → %s", success, failed, excel_path
    )
    return excel_path
