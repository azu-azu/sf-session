"""Salesforce Analytics Reports API wrapper with retry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .retry import call_with_retry

if TYPE_CHECKING:
    from simple_salesforce import Salesforce


def fetch_report_describe(sf: Salesforce, report_id: str) -> Any:
    """analytics/reports/{id}/describe を GET して JSON を返す。"""
    return call_with_retry(
        sf.restful, f"analytics/reports/{report_id}/describe", method="GET"
    )


def get_report_describe(
    sf: Salesforce,
    report_id: str,
    cache: dict[str, dict] | None = None,
) -> dict:
    """Report describe の共通取得エントリポイント。

    fetch + dict validation + optional cache。
    cache が渡されればキャッシュを使う。None なら毎回 fetch。
    API 例外はそのまま raise（呼び出し元で処理）。
    非 dict レスポンスは TypeError を raise。
    """
    if cache is not None and report_id in cache:
        return cache[report_id]
    result = fetch_report_describe(sf, report_id)
    if not isinstance(result, dict):
        raise TypeError(
            f"describe response is not a dict (report_id={report_id})"
        )
    if cache is not None:
        cache[report_id] = result
    return result


def parse_detail_meta(description: dict) -> tuple[list, dict]:
    """describe / run レスポンスから (detail_columns, col_info) を取り出す。

    reportMetadata.detailColumns と reportExtendedMetadata.detailColumnInfo を抽出する。
    どちらのキーも欠損していた場合は空リスト / 空 dict を返す。
    """
    report_metadata = description.get("reportMetadata", {}) or {}
    report_extended = description.get("reportExtendedMetadata", {}) or {}
    detail_columns: list = report_metadata.get("detailColumns") or []
    col_info: dict = report_extended.get("detailColumnInfo", {}) or {}
    return detail_columns, col_info


def get_column_label(col_info: dict, col_key: str) -> str:
    """col_info[col_key]['label'] を返す。エントリが無ければ col_key をそのまま返す。"""
    return col_info.get(col_key, {}).get("label", col_key)
