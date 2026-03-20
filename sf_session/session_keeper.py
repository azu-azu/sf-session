"""Salesforce session keeper.

Chrome をリモートデバッグモードで起動し、手動ログイン後に
定期リロードでセッションを維持する。
"""

import argparse
import logging
import subprocess
import sys
import time

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import WebDriverException
except ImportError:
    sys.exit(
        "selenium が見つからない。\n"
        "  pip install selenium\n"
        "ChromeDriver も PATH に必要。"
    )

from .config import CHROME_EXE_PATH, CHROME_USER_DATA_DIR, SF_BASE_URL

logger = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────
REMOTE_DEBUGGING_PORT = 9222
TARGET_URL = f"{SF_BASE_URL}/home/home.jsp"
KEEP_ALIVE_INTERVAL = 480  # seconds
CHROME_STARTUP_WAIT = 5  # seconds


def format_elapsed(seconds: float) -> str:
    """秒数を「x分x秒」形式にフォーマットする。60秒未満は小数1桁で表示。"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    m, s = divmod(int(seconds), 60)
    return f"{m}分{s}秒"


def launch_chrome(
    exe: str = CHROME_EXE_PATH,
    port: int = REMOTE_DEBUGGING_PORT,
    user_data_dir: str = CHROME_USER_DATA_DIR,
    url: str = TARGET_URL,
) -> subprocess.Popen:
    """Chrome をリモートデバッグモードで起動。"""
    cmd = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={user_data_dir}", url]
    logger.info("Chrome 起動: %s", " ".join(cmd))
    proc = subprocess.Popen(cmd)
    logger.info("Chrome PID: %d", proc.pid)
    return proc


def connect_driver(port: int = REMOTE_DEBUGGING_PORT) -> webdriver.Chrome:
    """起動済み Chrome に Selenium で接続。"""
    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    driver = webdriver.Chrome(options=opts)
    logger.info("WebDriver 接続完了: %s", driver.current_url)
    return driver


def keep_alive(driver: webdriver.Chrome, url: str, interval: int) -> None:
    """定期リロードでセッションを維持。Ctrl-C で停止。"""
    logger.info("keep-alive 開始 (interval=%s, url=%s)", format_elapsed(interval), url)
    try:
        while True:
            time.sleep(interval)
            driver.get(url)
            logger.info("reload → %s  title=%s", driver.current_url, driver.title)
    except KeyboardInterrupt:
        logger.info("Ctrl-C で停止")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Salesforce セッション keep-alive",
    )
    parser.add_argument(
        "--url",
        default=TARGET_URL,
        help=f"keep-alive 対象 URL (default: {TARGET_URL})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=KEEP_ALIVE_INTERVAL,
        help=f"リロード間隔 秒 (default: {KEEP_ALIVE_INTERVAL})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=REMOTE_DEBUGGING_PORT,
        help=f"リモートデバッグポート (default: {REMOTE_DEBUGGING_PORT})",
    )
    parser.add_argument(
        "--chrome-exe",
        default=CHROME_EXE_PATH,
        help="Chrome 実行ファイルパス",
    )
    parser.add_argument(
        "--user-data-dir",
        default=CHROME_USER_DATA_DIR,
        help="Chrome ユーザーデータディレクトリ",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Chrome を起動せず既存インスタンスに接続",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args(argv)

    chrome_proc = None
    driver = None
    try:
        # Chrome 起動
        if not args.no_launch:
            chrome_proc = launch_chrome(
                exe=args.chrome_exe, port=args.port,
                user_data_dir=args.user_data_dir, url=args.url,
            )
            time.sleep(CHROME_STARTUP_WAIT)

        # 手動ログイン待ち
        input("Chrome でログインしたら Enter を押す...（実行をキャンセルする場合は Ctrl + C を2回）")

        # Selenium 接続
        driver = connect_driver(port=args.port)

        # 初回遷移
        driver.get(args.url)
        logger.info("初回遷移: %s", driver.current_url)

        # keep-alive ループ
        keep_alive(driver, args.url, args.interval)

    except KeyboardInterrupt:
        logger.info("Ctrl-C で停止")
    except WebDriverException as e:
        logger.error("WebDriver エラー: %s", e)
        return 1
    except FileNotFoundError:
        logger.error("Chrome が見つからない: %s", args.chrome_exe)
        return 1
    finally:
        if driver:
            logger.info("WebDriver 終了")
            driver.quit()
        if chrome_proc and chrome_proc.poll() is None:
            logger.info("Chrome プロセス終了")
            chrome_proc.terminate()
            chrome_proc.wait(timeout=5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
