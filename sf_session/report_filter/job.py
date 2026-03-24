"""Salesforce レポートの probe job orchestrator.

指定されたレポート ID に対して describe API を呼び出し、
レポート名・列数を取得して Excel に書き出す。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceRefusedRequest

from ..config import SF_BASE_URL
from .analytics_api import (
    get_column_label,
    get_report_describe,
    parse_detail_meta,
)
from .job_result import JobResult, make_result
from .result_exporter import format_duration, write_result_excel

logger = logging.getLogger(__name__)

_NETWORK_ERRORS = (RequestsTimeout, RequestsConnectionError)


def _probe_single_report(
    sf: Salesforce,
    report_id: str,
    index: int,
    total: int,
    describe_cache: dict[str, dict],
) -> JobResult:
    """1 レポートの describe を実行して JobResult を返す。"""
    result = make_result(job_id=report_id)
    result.report_id = report_id
    result.report_url = f"{SF_BASE_URL}/{report_id}"

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

    result.status = "probed"
    result.finish(
        column_count=column_count,
        discovery_columns=columns,
    )

    logger.info(
        "  [%d/%d] %s — name=%s, cols=%d, %s",
        index,
        total,
        report_id,
        result.report_name,
        column_count,
        format_duration(result.duration_seconds),
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
