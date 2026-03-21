"""Extract report filters from Salesforce report describe payloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ._shared import extract_object_name
from .metadata import _as_non_empty_str
from .operators import (
    _DATE_LITERAL_RE,
    _OPERATOR_MAP,
    _SF_ID_RE,
    _build_column_type_map,
    _find_name_candidates,
    _not_contain_null_policy,
    _not_contain_strict_enabled,
    _render_literal,
)


@dataclass
class ExtractedFilter:
    source: str
    column: str | None
    operator: str | None
    values: list[Any]
    convertible: bool
    soql_clause: str | None
    reason: str | None = None
    assumption_used: str | None = None
    fallback_manual_reason: str | None = None
    relationship_name: str | None = None


@dataclass
class FilterExtractionResult:
    report_name: str | None
    report_type: str | None
    object_name: str | None
    report_boolean_filter: str | None
    filters: list[ExtractedFilter]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_name": self.report_name,
            "report_type": self.report_type,
            "object_name": self.object_name,
            "report_boolean_filter": self.report_boolean_filter,
            "filters": [asdict(f) for f in self.filters],
        }


def extract_filters_from_report_describe(payload: dict[str, Any]) -> FilterExtractionResult:
    metadata: dict[str, Any] = {}
    report_type_metadata: dict[str, Any] = {}

    if isinstance(payload, dict):
        raw_metadata = payload.get("reportMetadata", {})
        raw_report_type_metadata = payload.get("reportTypeMetadata", {})

        if (not raw_metadata or not raw_report_type_metadata) and isinstance(payload.get("describe"), dict):
            describe = payload["describe"]
            if not raw_metadata:
                raw_metadata = describe.get("reportMetadata", {})
            if not raw_report_type_metadata:
                raw_report_type_metadata = describe.get("reportTypeMetadata", {})

        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        report_type_metadata = (
            raw_report_type_metadata if isinstance(raw_report_type_metadata, dict) else {}
        )

    report_type = _extract_report_type(metadata.get("reportType"))
    column_type_map = _build_column_type_map(report_type_metadata)
    filters: list[ExtractedFilter] = []

    standard_date = metadata.get("standardDateFilter")
    if isinstance(standard_date, dict):
        filters.append(_extract_standard_date_filter(standard_date))

    standard_filters = metadata.get("standardFilters")
    if isinstance(standard_filters, list):
        filters.extend(
            _extract_generic_filter("standard_filter", item)
            for item in standard_filters
            if isinstance(item, dict)
        )

    report_filters = metadata.get("reportFilters")
    if isinstance(report_filters, list):
        filters.extend(
            _extract_generic_filter("report_filter", item)
            for item in report_filters
            if isinstance(item, dict)
        )

    cross_filters = metadata.get("crossFilters")
    if isinstance(cross_filters, list):
        filters.extend(
            _extract_unsupported(
                "cross_filter",
                item,
                "cross filter is not directly translatable to SOQL",
            )
            for item in cross_filters
            if isinstance(item, dict)
        )

    if column_type_map:
        filters = [_check_and_add_lookup_warning(f, column_type_map) for f in filters]

    return FilterExtractionResult(
        report_name=_as_non_empty_str(metadata.get("name")),
        report_type=report_type,
        object_name=extract_object_name(report_type),
        report_boolean_filter=_as_non_empty_str(metadata.get("reportBooleanFilter")),
        filters=filters,
    )


def _extract_standard_date_filter(item: dict[str, Any]) -> ExtractedFilter:
    column = _as_non_empty_str(item.get("column"))
    start = _as_non_empty_str(item.get("startDate"))
    end = _as_non_empty_str(item.get("endDate"))
    duration = _as_non_empty_str(item.get("durationValue"))

    if not column:
        return _extract_unsupported("standard_date_filter", item, "missing date filter column")

    if start and end:
        return ExtractedFilter(
            source="standard_date_filter",
            column=column,
            operator="between",
            values=[start, end],
            convertible=True,
            soql_clause=f"({column} >= {start} AND {column} <= {end})",
        )

    if start or end:
        return _extract_unsupported(
            "standard_date_filter",
            item,
            "date_range_incomplete",
        )

    if duration == "CUSTOM":
        return ExtractedFilter(
            source="standard_date_filter",
            column=column,
            operator="duration",
            values=[duration],
            convertible=True,
            soql_clause=None,
            reason="date_filter_not_effective",
        )

    if duration and _DATE_LITERAL_RE.fullmatch(duration):
        return ExtractedFilter(
            source="standard_date_filter",
            column=column,
            operator="duration",
            values=[duration],
            convertible=True,
            soql_clause=f"{column} = {duration}",
        )

    if duration:
        return _extract_unsupported(
            "standard_date_filter",
            item,
            "unsupported_date_duration_literal",
        )

    return _extract_unsupported(
        "standard_date_filter",
        item,
        "missing_date_filter_value",
    )


def _extract_generic_filter(source: str, item: dict[str, Any]) -> ExtractedFilter:
    column = _as_non_empty_str(item.get("column"))
    operator = _as_non_empty_str(item.get("operator"))
    values = _extract_values(item)

    if not column:
        return _extract_unsupported(source, item, "missing filter column")
    if not operator:
        return _extract_unsupported(source, item, "missing filter operator")

    if operator == "notContain":
        return _extract_not_contain_filter(source, column, operator, values)

    soql_operator = _OPERATOR_MAP.get(operator)
    if soql_operator is None:
        return _extract_unsupported(source, item, f"unsupported operator: {operator}")

    if operator in {"isNull", "notNull"}:
        return ExtractedFilter(
            source=source,
            column=column,
            operator=operator,
            values=[],
            convertible=True,
            soql_clause=f"{column} {soql_operator} NULL",
        )

    if soql_operator in {"IN", "NOT IN"}:
        if not values:
            return _extract_unsupported(source, item, "IN/NOT IN requires at least one value")
        rendered = ", ".join(_render_literal(v, for_date=False) for v in values)
        return ExtractedFilter(
            source=source,
            column=column,
            operator=operator,
            values=values,
            convertible=True,
            soql_clause=f"{column} {soql_operator} ({rendered})",
        )

    if not values:
        return _extract_unsupported(source, item, "operator requires a value")
    first = values[0]

    if operator == "contains":
        literal = _render_literal(f"%{first}%", for_date=False)
    elif operator == "startsWith":
        literal = _render_literal(f"{first}%", for_date=False)
    else:
        literal = _render_literal(first, for_date=("date" in column.lower()))

    return ExtractedFilter(
        source=source,
        column=column,
        operator=operator,
        values=values,
        convertible=True,
        soql_clause=f"{column} {soql_operator} {literal}",
    )


def _extract_values(item: dict[str, Any]) -> list[Any]:
    values = item.get("values")
    if isinstance(values, list):
        return [v for v in values if v is not None]
    if values is not None:
        return [values]

    value = item.get("value")
    if value is not None:
        return [value]

    return []


def _extract_unsupported(source: str, item: dict[str, Any], reason: str) -> ExtractedFilter:
    return ExtractedFilter(
        source=source,
        column=_as_non_empty_str(item.get("column")),
        operator=_as_non_empty_str(item.get("operator")),
        values=_extract_values(item),
        convertible=False,
        soql_clause=None,
        reason=reason,
        fallback_manual_reason=reason,
    )


def _extract_not_contain_filter(
    source: str,
    column: str,
    operator: str,
    values: list[Any],
) -> ExtractedFilter:
    if not _not_contain_strict_enabled():
        reason: str | None = "unsupported operator: notContain (strict mode off)"
    elif not values:
        reason = "operator requires a value"
    elif "%" in str(values[0]) or "_" in str(values[0]):
        reason = "wildcard_not_supported_for_notContain"
    else:
        reason = None

    if reason is not None:
        return ExtractedFilter(
            source=source,
            column=column,
            operator=operator,
            values=values,
            convertible=False,
            soql_clause=None,
            reason=reason,
            fallback_manual_reason=reason,
        )

    first = str(values[0])
    pattern = _render_literal(f"%{first}%", for_date=False)
    null_policy = _not_contain_null_policy()

    if null_policy == "A":
        clause = f"({column} = NULL OR NOT ({column} LIKE {pattern}))"
    else:
        clause = f"NOT ({column} LIKE {pattern})"

    return ExtractedFilter(
        source=source,
        column=column,
        operator=operator,
        values=values,
        convertible=True,
        soql_clause=clause,
        assumption_used=f"notContain_as_NOT_LIKE:null_policy{null_policy}",
    )


def _extract_report_type(raw: Any) -> str | None:
    if isinstance(raw, dict):
        return _as_non_empty_str(raw.get("type"))
    if isinstance(raw, str):
        return raw
    return None


def _check_and_add_lookup_warning(
    f: ExtractedFilter,
    column_type_map: dict[str, dict],
) -> ExtractedFilter:
    """lookup/id フィールドに非 SF-ID 値で比較している場合に assumption_used へ警告を付与する。"""
    if not f.convertible or not f.column or not f.values:
        return f
    if f.operator in {"isNull", "notNull"}:
        return f
    col_info = column_type_map.get(f.column)
    if not col_info:
        return f
    data_type = str(col_info.get("dataType") or "")
    is_lookup = col_info.get("isLookup") is True
    if not (data_type == "id" or is_lookup):
        return f
    first_val = str(f.values[0])
    if _SF_ID_RE.match(first_val):
        return f
    candidates = _find_name_candidates(f.column, column_type_map)
    warning = (
        f"lookup_non_sfid_value:candidates=[{','.join(candidates[:3])}]"
        if candidates
        else "lookup_non_sfid_value:no_candidates"
    )
    f.assumption_used = f"{f.assumption_used};{warning}" if f.assumption_used else warning
    return f
