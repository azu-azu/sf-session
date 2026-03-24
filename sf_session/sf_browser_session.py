"""Salesforce browser session の prepare / close を一元管理する共通層。

download.py と session_keeper.py の Chrome 起動 + Selenium 接続ロジックを
ここに集約し、重複を排除する。
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver

from .browser import (
    REMOTE_DEBUGGING_PORT,
    connect_driver,
    launch_chrome,
    try_connect_driver,
    wait_page_load,
)
from .config import CHROME_EXE_PATH, CHROME_USER_DATA_DIR, SF_HOME_URL
from .login_helper import ensure_logged_in

logger = logging.getLogger(__name__)

CHROME_STARTUP_WAIT = 5  # Chrome 起動後、Selenium 接続までの待機秒数


def _terminate_proc(proc: subprocess.Popen | None) -> None:
    """Popen を安全に terminate する。"""
    if proc and proc.poll() is None:
        logger.info("Chrome プロセス終了 (PID=%d)", proc.pid)
        proc.terminate()
        proc.wait(timeout=5)


@dataclass
class BrowserSession:
    """Chrome + WebDriver の session 情報。"""

    driver: WebDriver
    chrome_proc: subprocess.Popen | None = field(default=None, repr=False)

    @property
    def self_launched(self) -> bool:
        """このプロセスが Chrome を起動したかどうか。"""
        return self.chrome_proc is not None


def prepare_salesforce_session(
    *,
    port: int = REMOTE_DEBUGGING_PORT,
    chrome_exe: str = CHROME_EXE_PATH,
    user_data_dir: str | None = CHROME_USER_DATA_DIR,
    url: str = SF_HOME_URL,
    try_existing: bool = True,
) -> BrowserSession:
    """Salesforce にログイン済みの BrowserSession を返す。

    1. try_existing=True なら既存 Chrome への接続を試みる
    2. 接続できず user_data_dir ありなら Chrome を起動して接続
    3. navigate (self_launched なら skip — 起動時に url 指定済み)
    4. wait_page_load + ensure_logged_in
    5. BrowserSession を返す

    接続不可なら RuntimeError。caller が soft/hard fail を選ぶ。
    """
    driver: WebDriver | None = None
    chrome_proc: subprocess.Popen | None = None

    # 1. 既存 Chrome への接続を試みる
    if try_existing:
        driver = try_connect_driver(port=port)

    # 2. 接続できなければ Chrome を起動
    if driver is None:
        if user_data_dir is None:
            raise RuntimeError(
                "既存 Chrome に接続できず、user_data_dir 未指定のため起動もできない"
            )
        chrome_proc = launch_chrome(
            exe=chrome_exe, port=port,
            user_data_dir=user_data_dir, url=url,
        )
        time.sleep(CHROME_STARTUP_WAIT)
        try:
            driver = connect_driver(port=port)
        except Exception:
            _terminate_proc(chrome_proc)
            raise

    session = BrowserSession(driver=driver, chrome_proc=chrome_proc)

    # 3. navigate + login — 失敗時は Chrome を cleanup してから re-raise
    try:
        if not session.self_launched:
            driver.get(url)
        wait_page_load(driver)
        ensure_logged_in(driver)
    except Exception:
        close_browser_session(session)
        raise

    return session


def close_browser_session(session: BrowserSession) -> None:
    """driver.quit() + chrome_proc terminate。"""
    try:
        logger.info("WebDriver 終了")
        session.driver.quit()
    except Exception as e:
        logger.debug("driver.quit() failed: %s", e)

    _terminate_proc(session.chrome_proc)
