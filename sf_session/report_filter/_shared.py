"""report_filter サブパッケージ共通のヘルパー。"""

from __future__ import annotations

from typing import Any


def extract_object_name(report_type: str | dict[str, Any]) -> str | None:
    """reportType 値（str または dict）から Salesforce オブジェクト名を返す。

    Salesforce の reportType は "SomeName$ObjectName" 形式の文字列か、
    {"type": "SomeName$ObjectName", ...} 形式の dict で渡される。
    "$" の後ろが実際のオブジェクト名。
    """
    raw = str(report_type.get("type", "")) if isinstance(report_type, dict) else str(report_type or "")
    if not raw:
        return None
    return raw.split("$")[-1]
