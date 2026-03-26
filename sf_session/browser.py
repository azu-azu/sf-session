"""Chrome 起動・WebDriver 接続の共通モジュール。"""

from __future__ import annotations

import logging
import socket
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver

from .config import CHROME_EXE_PATH, CHROME_USER_DATA_DIR

logger = logging.getLogger(__name__)

REMOTE_DEBUGGING_PORT = 9222


def _import_selenium():
    """selenium を遅延 import して返す。未インストールなら ImportError。"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.support.ui import WebDriverWait
    return webdriver, Options, WebDriverException, WebDriverWait


def launch_chrome(
    exe: str = CHROME_EXE_PATH,
    port: int = REMOTE_DEBUGGING_PORT,
    user_data_dir: str = CHROME_USER_DATA_DIR,
    url: str = "",
) -> subprocess.Popen:
    """Chrome をリモートデバッグモードで起動。"""
    cmd = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={user_data_dir}"]
    if url:
        cmd.append(url)
    logger.info("Chrome 起動: %s", " ".join(cmd))
    proc = subprocess.Popen(cmd)
    logger.info("Chrome PID: %d", proc.pid)
    return proc


def connect_driver(port: int = REMOTE_DEBUGGING_PORT) -> WebDriver:
    """起動済み Chrome に Selenium で接続。"""
    webdriver, Options, _, _ = _import_selenium()
    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    driver = webdriver.Chrome(options=opts)
    logger.info("WebDriver 接続完了")
    return driver


def is_port_open(port: int, timeout: float = 1.0) -> bool:
    """port が listen 中か socket で高速チェック。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


def try_connect_driver(port: int = REMOTE_DEBUGGING_PORT) -> WebDriver | None:
    """接続を試み、失敗したら None を返す。

    先に socket で port が open か確認し、閉じていれば即 None を返す。
    Selenium の TCP timeout (~60秒) を回避するための fast path。
    """
    if not is_port_open(port):
        logger.debug("port %d は閉じている — 接続 skip", port)
        return None
    _, _, WebDriverException, _ = _import_selenium()
    try:
        return connect_driver(port)
    except WebDriverException as e:
        logger.debug("WebDriver 接続失敗: %s", e)
        return None


def wait_page_load(driver: WebDriver, timeout: int = 15) -> None:
    """document.readyState == 'complete' になるまで待機。"""
    _, _, _, WebDriverWait = _import_selenium()
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
