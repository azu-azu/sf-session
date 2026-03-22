"""Salesforce Analytics Reports API の薄いラッパー"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout
from simple_salesforce.exceptions import SalesforceError

if TYPE_CHECKING:
    from simple_salesforce import Salesforce

logger = logging.getLogger(__name__)


def fetch_report_describe(sf: Salesforce, report_id: str) -> Any:
    """analytics/reports/{id}/describe を GET して JSON を返す。"""
    return sf.restful(f"analytics/reports/{report_id}/describe", method="GET")


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


def get_object_describe_fields(
    sf: Salesforce,
    object_name: str,
    cache: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Object describe の fields[] をキャッシュ付きで返す。

    失敗時は空リストを返すが、キャッシュしない（一時エラーの固定化を防ぐ）。
    """
    if cache is not None and object_name in cache:
        return cache[object_name]
    try:
        described = getattr(sf, object_name).describe()
    except (SalesforceError, AttributeError, RequestsTimeout, RequestsConnectionError) as exc:
        logger.debug("object describe failed for %s: %s", object_name, exc)
        return []
    if not isinstance(described, dict):
        return []
    fields = described.get("fields")
    if not isinstance(fields, list):
        return []
    result = [f for f in fields if isinstance(f, dict)]
    if cache is not None:
        cache[object_name] = result
    return result


def fetch_report_run(sf: Salesforce, report_id: str) -> Any:
    """analytics/reports/{id} を GET してレポート実行結果の JSON を返す。"""
    return sf.restful(f"analytics/reports/{report_id}", method="GET")
