"""SF ログイン検出・SSO 手動ログイン待機・MFA 完了待ち。"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver

logger = logging.getLogger(__name__)

# ── 定数 ──────────────────────────────────────────────────
MFA_TIMEOUT = 600  # seconds (10分)
MAX_LOGIN_RETRIES = 2  # 初回 + 1回 retry
OFF_SF_PATIENCE = 30  # SF ドメイン外での最大待機 (秒)


# ── 例外 ──────────────────────────────────────────────────


class MfaTimeoutError(TimeoutError):
    """MFA 待機が timeout。retry 対象。"""


class AuthFlowLeftError(TimeoutError):
    """認証フロー外に遷移（SSO キャンセル等）。retry しても無駄。"""


class LoginPageReturnedError(TimeoutError):
    """Login page に戻された（session expire 等）。retry しても無駄。"""


class LoginExhaustedError(RuntimeError):
    """ログイン retry 回数を使い切った。"""

# ── ページ判定 ────────────────────────────────────────────


def _is_sf_domain(url: str) -> bool:
    """URL が SF 関連ドメインか判定。"""
    return "force.com" in url or "salesforce.com" in url


def is_login_page(driver: WebDriver) -> bool:
    """SF ログインページか判定。URL + #username/#password 要素で判定。"""
    url = driver.current_url.lower()
    if "login.salesforce.com" not in url and "/login" not in url:
        return False
    try:
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException
        driver.find_element(By.ID, "username")
        driver.find_element(By.ID, "password")
        return True
    except NoSuchElementException:
        return False


def is_sso_page(driver: WebDriver) -> bool:
    """SSO ページか判定。URL に 'sso' を含むかで判定。"""
    return "sso" in driver.current_url.lower()


def is_mfa_page(driver: WebDriver) -> bool:
    """MFA 認証ページか判定。暫定: URL に verify/identity を含むか判定。"""
    url = driver.current_url.lower()
    return "verify" in url or "/identity/" in url


def is_logged_in(driver: WebDriver) -> bool:
    """ログイン完了状態か判定。"""
    url = driver.current_url.lower()
    return (
        not is_login_page(driver)
        and not is_mfa_page(driver)
        and _is_sf_domain(url)
    )


# ── ログイン待機 ──────────────────────────────────────────


def wait_until_logged_in(
    driver: WebDriver,
    poll: float = 2.0,
    *,
    timeout: float = MFA_TIMEOUT,
) -> None:
    """ログイン完了まで待機。

    Raises:
        MfaTimeoutError: timeout 超過（retry 対象）
        LoginPageReturnedError: login page に戻された（回復不能）
        AuthFlowLeftError: 認証フロー外に遷移（回復不能）
    """
    logger.info("MFA / ログイン完了を待機中... (timeout=%ds)", timeout)
    elapsed = 0.0
    elapsed_off_sf = 0.0
    try:
        while not is_logged_in(driver):
            time.sleep(poll)
            elapsed += poll

            # 1回だけ取得して全判定に使い回す (Selenium RPC 削減)
            url = driver.current_url.lower()
            on_login = is_login_page(driver)
            on_mfa = is_mfa_page(driver)

            # SF が session expire → login page に戻されるケースを検出
            if on_login:
                raise LoginPageReturnedError(
                    f"login page へ戻された ({elapsed:.0f}s経過)"
                )

            # SF ドメイン外に長時間いる → 認証キャンセルやエラー
            on_sso = "sso" in url
            if _is_sf_domain(url) or on_mfa or on_sso:
                elapsed_off_sf = 0.0
            else:
                elapsed_off_sf += poll
                if elapsed_off_sf >= OFF_SF_PATIENCE:
                    raise AuthFlowLeftError(
                        f"認証フロー外に遷移 ({elapsed_off_sf:.0f}s): "
                        f"{driver.current_url}"
                    )

            if elapsed >= timeout:
                raise MfaTimeoutError(
                    f"MFA 待機が {timeout:.0f}s でタイムアウト"
                )

            if elapsed % 30 < poll:
                logger.info("MFA 待機中... (%.0f秒経過)", elapsed)
    except KeyboardInterrupt:
        logger.info("MFA 待機を Ctrl+C で中断")
        raise


def ensure_logged_in(
    driver: WebDriver,
    *,
    max_retries: int = MAX_LOGIN_RETRIES,
) -> bool:
    """ログイン済みなら False、未ログインなら手動ログイン待機 → True。

    SSO or ログインページ検出時は手動ログインを促し wait_until_logged_in() で待機。
    MFA timeout 時は max_retries 回までリトライ。
    認証フロー離脱・login page 戻りは回復不能として即失敗。
    全 retry 消費 or 回復不能エラーで LoginExhaustedError を raise。

    Returns:
        True: ログイン処理を実行した
        False: 既にログイン済みだった
    """
    if is_logged_in(driver):
        logger.info("既にログイン済み — skip")
        return False

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "手動でログインしてください (attempt %d/%d)",
                attempt, max_retries,
            )
            wait_until_logged_in(driver)

            logger.info("ログイン完了: %s", driver.current_url)
            return True

        except (AuthFlowLeftError, LoginPageReturnedError) as e:
            logger.warning("回復不能: %s", e)
            raise LoginExhaustedError(str(e)) from e

        except MfaTimeoutError as e:
            logger.warning(
                "auth failed: %s (attempt %d/%d)", e, attempt, max_retries,
            )
            if attempt >= max_retries:
                raise LoginExhaustedError(
                    f"ログイン retry 回数上限 ({max_retries}) に到達"
                ) from e
            continue

    # ここには到達しないが型チェッカー対策
    raise LoginExhaustedError("unreachable")


# ── タブ traverse ─────────────────────────────────────────


def find_login_tab(driver: WebDriver) -> bool:
    """全タブを traverse してログインページ/MFA/SSO ページを探す。

    見つかったらそのタブに switch した状態で True を返す。
    見つからなければ元のタブに戻して False を返す。
    """
    original = driver.current_window_handle
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if is_login_page(driver) or is_mfa_page(driver) or is_sso_page(driver):
            return True
    driver.switch_to.window(original)
    return False
