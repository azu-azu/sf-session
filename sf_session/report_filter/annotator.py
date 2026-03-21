"""Filter parity annotation and auto/manual classification."""

from __future__ import annotations

from typing import Any

from .metadata import _as_non_empty_str


def _split_auto_manual(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition *results* into (auto-convertible, manual) lists."""
    auto_results: list[dict[str, Any]] = []
    manual_results: list[dict[str, Any]] = []
    for item in results:
        if _is_auto_convertible(item):
            auto_results.append(item)
        else:
            manual_results.append(item)
    return auto_results, manual_results


def _is_auto_convertible(item: dict[str, Any]) -> bool:
    """Return True when *item* is fully convertible to SOQL without manual intervention."""
    parity_status = item.get("parity_status")
    if isinstance(parity_status, str):
        return parity_status == "auto"

    if item.get("status") != "success":
        return False

    filters = item.get("filters")
    if not isinstance(filters, list) or not filters:
        return False

    return all(isinstance(f, dict) and f.get("convertible") is True for f in filters)


def _annotate_parity(item: dict[str, Any]) -> None:
    """Set ``parity_status`` and ``parity_reason`` in-place on *item*."""
    filters = item.get("filters")
    if not isinstance(filters, list) or not filters:
        item["parity_status"] = "manual"
        item["parity_reason"] = "filters_empty"
        return

    has_custom_missing = any(
        isinstance(f, dict) and f.get("reason") == "custom_date_range_missing"
        for f in filters
    )
    if has_custom_missing:
        item["parity_status"] = "manual"
        item["parity_reason"] = "custom_date_range_missing"
        return

    has_non_convertible = any(
        not (isinstance(f, dict) and f.get("convertible") is True)
        for f in filters
    )
    if has_non_convertible:
        item["parity_status"] = "manual"
        item["parity_reason"] = "non_convertible_filter"
        return

    item["parity_status"] = "auto"


def _fill_custom_date_ranges(item: dict[str, Any], report_result: dict[str, Any]) -> None:
    """Backfill startDate/endDate into standard_date_filter entries that were missing them."""
    report_metadata = report_result.get("reportMetadata")
    if not isinstance(report_metadata, dict):
        return
    sdf = report_metadata.get("standardDateFilter")
    if not isinstance(sdf, dict):
        return

    start = _as_non_empty_str(sdf.get("startDate"))
    end = _as_non_empty_str(sdf.get("endDate"))
    column = _as_non_empty_str(sdf.get("column"))
    if not start or not end:
        return

    filters = item.get("filters")
    if not isinstance(filters, list):
        return

    for f in filters:
        if not isinstance(f, dict):
            continue
        if f.get("source") != "standard_date_filter":
            continue
        if f.get("reason") != "custom_date_range_missing":
            continue

        filter_column = _as_non_empty_str(f.get("column"))
        if column and filter_column and column != filter_column:
            continue

        f["operator"] = "between"
        f["values"] = [start, end]
        f["convertible"] = True
        f["soql_clause"] = f"({filter_column or column} >= {start} AND {filter_column or column} <= {end})"
        f["reason"] = None
