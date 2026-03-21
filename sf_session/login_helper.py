"""SF ログインページの自動検出・ID/PW 入力・MFA 完了待ち。"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver

from .browser import wait_page_load

logger = logging.getLogger(__name__)

# ── ページ判定 ────────────────────────────────────────────


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
        and "salesforce.com" in url
    )


# ── ログイン操作 ──────────────────────────────────────────


def fill_credentials(driver: WebDriver, username: str, password: str) -> None:
    """ID/PW を入力して Login ボタンをクリック。"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    wait = WebDriverWait(driver, 15)

    user_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
    user_field.clear()
    user_field.send_keys(username)

    pass_field = driver.find_element(By.ID, "password")
    pass_field.clear()
    pass_field.send_keys(password)

    login_btn = driver.find_element(By.ID, "Login")
    login_btn.click()
    logger.info("credentials 入力 + Login クリック完了")


def wait_until_logged_in(driver: WebDriver, poll: float = 2.0) -> None:
    """MFA 完了まで待機。timeout なし。Ctrl+C で中断可能。"""
    logger.info("MFA / ログイン完了を待機中...")
    elapsed = 0.0
    try:
        while not is_logged_in(driver):
            time.sleep(poll)
            elapsed += poll
            if elapsed % 30 < poll:
                logger.info("MFA 待機中... (%.0f秒経過)", elapsed)
    except KeyboardInterrupt:
        logger.info("MFA 待機を Ctrl+C で中断")
        raise


def ensure_logged_in(driver: WebDriver, username: str, password: str) -> bool:
    """ログイン済みなら False、ログインが必要なら自動入力 + MFA 待ち → True。

    Returns:
        True: ログイン処理を実行した
        False: 既にログイン済みだった
    """
    if is_logged_in(driver):
        logger.info("既にログイン済み — skip")
        return False

    if is_login_page(driver):
        logger.info("ログインページ検出 — credentials 自動入力")
        fill_credentials(driver, username, password)
        wait_page_load(driver)

    if is_mfa_page(driver):
        wait_until_logged_in(driver)
    elif not is_logged_in(driver):
        # Login 後にリダイレクト待ちが必要なケース
        wait_until_logged_in(driver)

    logger.info("ログイン完了: %s", driver.current_url)
    return True


# ── タブ走査 ──────────────────────────────────────────────


def find_login_tab(driver: WebDriver) -> bool:
    """全タブを走査してログインページ/MFA ページを探す。

    見つかったらそのタブに switch した状態で True を返す。
    見つからなければ元のタブに戻して False を返す。
    """
    original = driver.current_window_handle
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if is_login_page(driver) or is_mfa_page(driver):
            return True
    driver.switch_to.window(original)
    return False
