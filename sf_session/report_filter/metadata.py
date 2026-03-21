"""Metadata payload construction for report filter extraction."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _as_non_empty_str(value: Any) -> str | None:
    """Convert *value* to a stripped string, returning None for empty/None values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_column_count(description: dict[str, Any]) -> int | None:
    """Return the number of detail columns declared in *description*, or None if unavailable."""
    metadata = description.get("reportMetadata")
    if not isinstance(metadata, dict):
        return None
    detail_columns = metadata.get("detailColumns")
    if not isinstance(detail_columns, list):
        return None
    return len(detail_columns)


def _to_bool_or_none(value: Any) -> bool | None:
    """Return bool(value) if value is not None, else None."""
    return bool(value) if value is not None else None


def _extract_row_count(report_result: dict[str, Any]) -> tuple[int | None, bool | None]:
    """Return (max_row_count, all_data_flag) extracted from a report run result."""
    fact_map = report_result.get("factMap")
    if not isinstance(fact_map, dict):
        return None, None

    max_rows = 0
    has_any_row_array = False
    for value in fact_map.values():
        if not isinstance(value, dict):
            continue
        rows = value.get("rows")
        if isinstance(rows, list):
            has_any_row_array = True
            max_rows = max(max_rows, len(rows))

    all_data = _to_bool_or_none(report_result.get("allData"))
    if not has_any_row_array:
        return 0, all_data
    return max_rows, all_data


def _slim_object_fields(raw_fields: list[dict]) -> list[dict[str, str]]:
    """Extract only name/label/type from raw Object describe fields."""
    return [
        {"name": f["name"], "label": f["label"], "type": f["type"]}
        for f in raw_fields
        if isinstance(f, dict) and "name" in f and "label" in f and "type" in f
    ]


def _build_report_metadata_payload(
    report_id: str,
    *,
    description: dict[str, Any] | None,
    report_result: dict[str, Any] | None,
    status: str,
    error: str | None = None,
    from_object: str | None = None,
    object_fields: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a structured metadata snapshot for one report."""
    desc = description if isinstance(description, dict) else {}
    describe_meta = desc.get("reportMetadata")
    result_meta = report_result.get("reportMetadata") if isinstance(report_result, dict) else None
    fact_map = report_result.get("factMap") if isinstance(report_result, dict) else None

    payload: dict[str, Any] = {
        "report_id": report_id,
        "status": status,
        "captured_at": datetime.now(UTC).isoformat(),
        "from_object": from_object,
        "object_fields": object_fields,
        "report_format": _extract_report_format(describe_meta, result_meta),
        "factmap_keys": _extract_factmap_keys(fact_map),
        "grouping": _extract_grouping_info(describe_meta, result_meta, report_result),
        "sortby": _extract_sortby(describe_meta, result_meta),
        "describe": {
            "reportMetadata": _jsonable_or_none(describe_meta),
            "reportTypeMetadata": _jsonable_or_none(desc.get("reportTypeMetadata")),
            "reportExtendedMetadata": _jsonable_or_none(desc.get("reportExtendedMetadata")),
            "attributes": _jsonable_or_none(desc.get("attributes")),
        },
        "result": {
            "reportMetadata": _jsonable_or_none(result_meta),
            "factMapSummary": _build_factmap_summary(fact_map),
            "allData": _to_bool_or_none(report_result.get("allData")) if isinstance(report_result, dict) else None,
            "hasDetailRows": (
                _to_bool_or_none(report_result.get("hasDetailRows")) if isinstance(report_result, dict) else None
            ),
        },
    }
    if error:
        payload["error"] = error
    return payload


def _build_factmap_summary(fact_map: Any) -> dict[str, Any] | None:
    """Summarise a factMap dict into row/aggregate counts per key, or None if invalid."""
    if not isinstance(fact_map, dict):
        return None

    blocks: dict[str, Any] = {}
    for key, value in fact_map.items():
        if not isinstance(value, dict):
            blocks[str(key)] = {"type": type(value).__name__}
            continue
        rows = value.get("rows")
        aggregates = value.get("aggregates")
        blocks[str(key)] = {
            "row_count": len(rows) if isinstance(rows, list) else None,
            "aggregate_count": len(aggregates) if isinstance(aggregates, list) else None,
            "has_rows": bool(rows) if isinstance(rows, list) else False,
        }

    return {"keys": list(blocks.keys()), "blocks": blocks}


def _extract_report_format(describe_meta: Any, result_meta: Any) -> str | None:
    """Return reportFormat from describe metadata, falling back to result metadata."""
    if isinstance(describe_meta, dict):
        value = _as_non_empty_str(describe_meta.get("reportFormat"))
        if value:
            return value
    if isinstance(result_meta, dict):
        return _as_non_empty_str(result_meta.get("reportFormat"))
    return None


def _extract_factmap_keys(fact_map: Any) -> list[str]:
    """Return the string-coerced keys of a factMap dict, or an empty list."""
    if not isinstance(fact_map, dict):
        return []
    return [str(k) for k in fact_map]


def _first_dict_get(a: Any, b: Any, key: str) -> Any:
    """Return a[key] if a is a dict, else b[key] if b is a dict, else None."""
    if isinstance(a, dict):
        return a.get(key)
    if isinstance(b, dict):
        return b.get(key)
    return None


def _extract_grouping_info(
    describe_meta: Any,
    result_meta: Any,
    report_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Collect groupingsDown/groupingsAcross from both describe and result metadata."""
    rr = report_result if isinstance(report_result, dict) else {}
    return {
        "reportMetadata.groupingsDown": _jsonable_or_none(_first_dict_get(describe_meta, result_meta, "groupingsDown")),
        "reportMetadata.groupingsAcross": _jsonable_or_none(
            _first_dict_get(describe_meta, result_meta, "groupingsAcross")
        ),
        "result.groupingsDown": _jsonable_or_none(rr.get("groupingsDown")),
        "result.groupingsAcross": _jsonable_or_none(rr.get("groupingsAcross")),
    }


def _extract_sortby(describe_meta: Any, result_meta: Any) -> Any:
    """Return sortBy from describe metadata, falling back to result metadata."""
    if isinstance(describe_meta, dict) and describe_meta.get("sortBy") is not None:
        return _jsonable_or_none(describe_meta.get("sortBy"))
    if isinstance(result_meta, dict):
        return _jsonable_or_none(result_meta.get("sortBy"))
    return None


def _jsonable_or_none(value: Any) -> Any:
    """Return a JSON-serialisable representation of *value*, or None."""
    if value is None:
        return None
    return _to_jsonable(value)


def _to_jsonable(value: Any) -> Any:
    """Recursively convert *value* to a JSON-serialisable primitive."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return str(value)
