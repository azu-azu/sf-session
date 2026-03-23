"""Salesforce session keeper.

Chrome をリモートデバッグモードで起動し、自動ログイン（MFA は手動待ち）後に
定期リロードでセッションを維持する。
"""

import argparse
import logging
import sys
import time

from selenium.common.exceptions import WebDriverException

from .browser import (
    REMOTE_DEBUGGING_PORT,
    launch_chrome,
    connect_driver,
    wait_page_load,
)
from .config import CHROME_EXE_PATH, CHROME_USER_DATA_DIR, SF_HOME_URL, get_login_credentials
from .login_helper import ensure_logged_in

logger = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────
KEEP_ALIVE_INTERVAL = 480  # session 維持のための reload 間隔 (秒)
CHROME_STARTUP_WAIT = 5  # Chrome 起動後、Selenium 接続までの待機時間 (秒)


def format_elapsed(seconds: float) -> str:
    """秒数を「x分x秒」形式にフォーマットする。60秒未満は小数1桁で表示。"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    m, s = divmod(int(seconds), 60)
    return f"{m}分{s}秒"


def keep_alive(driver, url: str, interval: int) -> None:
    """定期リロードでセッションを維持。Ctrl-C で停止。"""
    logger.info("keep-alive 開始 (interval=%s, url=%s)", format_elapsed(interval), url)
    while True:
        time.sleep(interval)
        driver.get(url)
        logger.info("reload → %s  title=%s", driver.current_url, driver.title)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Salesforce セッション keep-alive",
    )
    parser.add_argument(
        "--url",
        default=SF_HOME_URL,
        help=f"keep-alive 対象 URL (default: {SF_HOME_URL})",
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

        # Selenium 接続
        driver = connect_driver(port=args.port)

        # 初回遷移 + ページ読み込み待ち
        # 自前起動の場合は既に args.url に遷移済み → reload しない
        if args.no_launch:
            driver.get(args.url)
        wait_page_load(driver)

        # 自動ログイン（MFA は手動待ち）
        username, password = get_login_credentials()
        ensure_logged_in(driver, username, password)

        logger.info("初回遷移: %s", driver.current_url)

        # keep-alive ループ
        keep_alive(driver, args.url, args.interval)

    except KeyboardInterrupt:
        logger.info("Ctrl-C で停止")
    except FileNotFoundError:
        logger.error("Chrome が見つからない: %s", args.chrome_exe)
        return 1
    except WebDriverException as e:
        logger.error("WebDriver エラー: %s", e)
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
