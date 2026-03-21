"""Operator mapping and value-rendering utilities for report filter extraction."""

from __future__ import annotations

import os
import re
from typing import Any

# インライン化した定数
_NOT_CONTAIN_STRICT_ENV = "SF_NOTCONTAIN_STRICT"
_NOT_CONTAIN_NULL_POLICY_ENV = "SF_NOTCONTAIN_NULL_POLICY"
_TRUTHY = {"1", "true", "yes", "on"}

_DATE_LITERAL_RE = re.compile(r"^[A-Z_]+(?::\d+)?$")

_SF_ID_RE = re.compile(r"^[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?$")

_OPERATOR_MAP = {
    "equals": "=",
    "eq": "=",
    "=": "=",
    "notEqual": "!=",
    "ne": "!=",
    "!=": "!=",
    "greaterThan": ">",
    "gt": ">",
    ">": ">",
    "greaterOrEqual": ">=",
    "ge": ">=",
    ">=": ">=",
    "lessThan": "<",
    "lt": "<",
    "<": "<",
    "lessOrEqual": "<=",
    "le": "<=",
    "<=": "<=",
    "contains": "LIKE",
    "startsWith": "LIKE",
    "in": "IN",
    "includes": "IN",
    "notIn": "NOT IN",
    "excludes": "NOT IN",
    "isNull": "=",
    "notNull": "!=",
}


def _render_literal(value: Any, *, for_date: bool) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)

    text = str(value)
    is_date_literal = for_date and bool(_DATE_LITERAL_RE.match(text))
    if is_date_literal:
        return text

    escaped = text.replace("'", "\\'")
    return f"'{escaped}'"


def _not_contain_strict_enabled() -> bool:
    raw = os.environ.get(_NOT_CONTAIN_STRICT_ENV, "")
    return raw.strip().lower() in _TRUTHY


def _not_contain_null_policy() -> str:
    raw = os.environ.get(_NOT_CONTAIN_NULL_POLICY_ENV, "A").strip().upper()
    if raw in {"A", "B"}:
        return raw
    return "A"


def _build_column_type_map(report_type_metadata: dict) -> dict[str, dict]:
    """reportTypeMetadata.categories からフィールド名 -> メタ情報のマップを構築する。"""
    col_map: dict[str, dict] = {}
    if not isinstance(report_type_metadata, dict):
        return col_map
    categories = report_type_metadata.get("categories", [])
    if not isinstance(categories, list):
        return col_map
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        columns = cat.get("columns", {})
        if not isinstance(columns, dict):
            continue
        for info in columns.values():
            if not isinstance(info, dict):
                continue
            for attr in ("fullyQualifiedName", "entityColumnName"):
                fqn = info.get(attr)
                if isinstance(fqn, str) and fqn and fqn not in col_map:
                    col_map[fqn] = info
    return col_map


def _find_name_candidates(column: str, column_type_map: dict[str, dict]) -> list[str]:
    """同一オブジェクトの string 型フィールドを候補として返す（Name 系を優先）。"""
    m = re.match(r"^([A-Za-z0-9_]+)\.", column)
    if not m:
        return []
    prefix = m.group(1) + "."
    seen: set[str] = set()
    name_first: list[str] = []
    others: list[str] = []
    for fqn, info in column_type_map.items():
        if not fqn.startswith(prefix) or fqn == column:
            continue
        if str(info.get("dataType") or "") not in ("string", "text", "textarea"):
            continue
        if fqn in seen:
            continue
        seen.add(fqn)
        if fqn.endswith(".Name"):
            name_first.append(fqn)
        else:
            others.append(fqn)
    return name_first + others
