"""Salesforce session keeper.

Chrome をリモートデバッグモードで起動し、手動ログイン待機（SSO / MFA）後に
定期リロードでセッションを維持する。
"""

import argparse
import logging
import sys
import time

from selenium.common.exceptions import WebDriverException

from .browser import REMOTE_DEBUGGING_PORT
from .config import CHROME_EXE_PATH, CHROME_USER_DATA_DIR, SF_HOME_URL
from .session import (
    BrowserSession,
    close_browser_session,
    prepare_salesforce_session,
)
from .utils import format_duration

logger = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────
KEEP_ALIVE_INTERVAL = 480  # session 維持のための reload 間隔 (秒)


def keep_alive(driver, url: str, interval: int) -> None:
    """定期リロードでセッションを維持。Ctrl-C で停止。"""
    logger.info("keep-alive 開始 (interval=%s, url=%s)", format_duration(interval), url)
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

    session: BrowserSession | None = None
    try:
        session = prepare_salesforce_session(
            port=args.port,
            chrome_exe=args.chrome_exe,
            user_data_dir=args.user_data_dir if not args.no_launch else None,
            url=args.url,
            try_existing=args.no_launch,
        )
        logger.info("初回遷移: %s", session.driver.current_url)
        keep_alive(session.driver, args.url, args.interval)

    except KeyboardInterrupt:
        logger.info("Ctrl-C で停止")
    except FileNotFoundError:
        logger.error("Chrome が見つからない: %s", args.chrome_exe)
        return 1
    except RuntimeError as e:
        logger.error("セッション準備失敗: %s", e)
        return 1
    except WebDriverException as e:
        logger.error("WebDriver エラー: %s", e)
        return 1
    finally:
        if session:
            close_browser_session(session)

    return 0


if __name__ == "__main__":
    sys.exit(main())
