"""Retry / exponential backoff helper for Salesforce API calls."""

from __future__ import annotations

import logging
import time
from typing import Any

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_BASE_WAIT = 2.0  # seconds: 2s → 4s → fail

_RETRYABLE_NETWORK_EXCEPTIONS = (RequestsTimeout, RequestsConnectionError)


def _is_retryable(exc: Exception) -> bool:
    """429 または 5xx のみリトライ対象とする。"""
    status = getattr(exc, "status", None)
    if status is None:
        return False
    return status == 429 or status >= 500


def call_with_retry(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """fn(*args, **kwargs) を最大 _MAX_ATTEMPTS 回、指数バックオフで実行する。

    リトライ対象:
      - SalesforceError のうち status が 429 または 5xx のもの
      - requests.exceptions.Timeout / ConnectionError（一時的なネットワーク障害）

    最終失敗時は元の例外をそのまま raise。
    """
    from simple_salesforce.exceptions import SalesforceError

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except SalesforceError as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
        except _RETRYABLE_NETWORK_EXCEPTIONS as exc:
            last_exc = exc

        if attempt < _MAX_ATTEMPTS - 1:
            wait = _BASE_WAIT * (2**attempt)
            logger.warning(
                "Retryable error (attempt %d/%d, %s): %s — retrying in %.1fs",
                attempt + 1,
                _MAX_ATTEMPTS,
                type(last_exc).__name__,
                last_exc,
                wait,
            )
            time.sleep(wait)

    if last_exc is None:
        raise RuntimeError("call_with_retry: loop exited without exception")

    logger.error(
        "All %d attempts failed (%s): %s",
        _MAX_ATTEMPTS,
        type(last_exc).__name__,
        last_exc,
    )
    raise last_exc
