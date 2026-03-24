"""VBA procSalseForce の Python 移植 — バッチ export スクリプト。

ログイン済み Chrome で Salesforce export URL を順次開き、
Downloads フォルダを監視して新規ファイルを移動先にリネーム・コピーする。

Usage:
    python -m sf_session.download --dry-run
    python -m sf_session.download --ids-file
    python -m sf_session.download --retry
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from .config import (
    CHROME_EXE_PATH,
    CHROME_USER_DATA_DIR,
    CSV_STAGING_DIR,
    CSV_STAGING_ROOT,
    DEFAULT_IDS_FILE,
    MACRO_DIR,
    SF_HOME_URL,
)
from .browser import REMOTE_DEBUGGING_PORT
from .business_day import should_run_download
from .macro_book_reader import load_active_jobs
from .utils import setup_logging
from ._download_single import (
    build_export_url,
    ensure_exists,
    resolve_download_dir,
)
from .download_runner import (
    DEFAULT_TIMEOUT,
    DEFAULT_POLL,
    DEFAULT_INTERVAL,
    export_batch,
)
from .download_outputs import (
    build_destination,
    log_summary,
    open_folder,
    prepare_work_dir,
    probe_output_dir,
    swap_work_to_staging,
    write_marker,
    write_success_ids,
)
from .sf_browser_session import (
    BrowserSession,
    close_browser_session,
    prepare_salesforce_session,
)

logger = logging.getLogger(__name__)


# ── internal helpers ─────────────────────────────────────


def _resolve_user_data_dir(args: argparse.Namespace) -> Path | None:
    """--my-chrome 処理を含む user_data_dir 解決。"""
    if args.my_chrome:
        if args.user_data_dir != CHROME_USER_DATA_DIR:
            logger.warning("--my-chrome が指定されたため --user-data-dir は無視されます")
        return None

    if not args.user_data_dir:
        return None

    resolved = Path(args.user_data_dir).expanduser().resolve()
    ensure_exists(resolved, "Chrome user data dir")
    return resolved


def _log_run_config(
    chrome_path: Path,
    download_dir: Path,
    user_data_dir: Path | None,
    args: argparse.Namespace,
    output_dir: Path | None,
) -> None:
    """設定値をログ出力。"""
    logger.info("Chrome      : %s", chrome_path)
    logger.info("Downloads   : %s", download_dir)
    if user_data_dir is not None:
        logger.info("UserDataDir : %s", user_data_dir)
    if args.profile_directory:
        logger.info("Profile     : %s", args.profile_directory)
    logger.info("Port        : %d", args.port)
    logger.info("Timeout     : %ds", args.timeout)
    logger.info("date-suffix : %s", args.date_suffix)
    if output_dir:
        logger.info("Output dir  : %s", output_dir)
    else:
        logger.info("Output mode : direct-deliver (per-job)")


def _print_dry_run(args: argparse.Namespace, jobs) -> None:
    """dry-run モードのジョブ一覧表示。"""
    if not args.direct_deliver:
        logger.info("Output dir  : %s", CSV_STAGING_DIR)
    logger.info("--- dry-run mode ---")
    dummy_dl = Path("{download}")
    for i, j in enumerate(jobs, 1):
        rid = j.report_id or "(なし)"
        enc = j.encode if j.encode else "Shift_JIS"
        url = build_export_url(rid, enc=enc) if j.report_id else "(URL 構築不可)"
        if not args.direct_deliver:
            dest = build_destination(
                j, dummy_dl,
                date_suffix=args.date_suffix,
                output_dir=CSV_STAGING_DIR,
            )
        else:
            dest = j.src_folder_name
        logger.info(
            "  %d件目  %s  enc=%s  → %s",
            i, rid, enc, dest,
        )
        logger.info("           %s", url)


# ── CLI ──────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VBA procSalseForce 相当 — バッチ export スクリプト",
    )
    parser.add_argument(
        "--chrome-path",
        default=CHROME_EXE_PATH,
        help=f"Chrome 実行ファイルパス (default: {CHROME_EXE_PATH})",
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Downloads フォルダ (default: ~/Downloads)",
    )
    parser.add_argument(
        "--my-chrome",
        action="store_true",
        help="普段使いの Chrome で実行 (session_keeper の専用プロファイルではなく OS デフォルト)",
    )
    parser.add_argument(
        "--user-data-dir",
        default=CHROME_USER_DATA_DIR,
        help=f"Chrome user data dir (default: {CHROME_USER_DATA_DIR})",
    )
    parser.add_argument(
        "--profile-directory",
        default=None,
        help='Chrome profile directory name, e.g. "Default" or "Profile 1"',
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Per-report timeout 秒 (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=DEFAULT_POLL,
        help=f"Poll interval 秒 (default: {DEFAULT_POLL})",
    )
    parser.add_argument(
        "--date-suffix",
        action="store_true",
        help="ファイル名に _YYYYMMDD を付与 (VBA CheckBox1 相当)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"レポート間 wait 秒 (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--macro-dir",
        type=Path,
        default=MACRO_DIR,
        help=f"マクロ格納フォルダ path (default: {MACRO_DIR})",
    )
    parser.add_argument(
        "--ids-file",
        action="store_true",
        default=False,
        help=f"{DEFAULT_IDS_FILE} から report ID を読み取り、ジョブ定義との intersection でフィルタ",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        default=False,
        help="前回の success_ids を読み、成功済みを除外して失敗分だけ再実行",
    )
    parser.add_argument(
        "--direct-deliver",
        action="store_true",
        help="per-job 振り分け先フォルダへ直接コピー (default: outputs_csv/ に全出力)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=REMOTE_DEBUGGING_PORT,
        help=f"Chrome リモートデバッグポート (default: {REMOTE_DEBUGGING_PORT})",
    )
    parser.add_argument(
        "--no-login-check",
        action="store_true",
        help="起動時の pre-flight login check を skip",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="営業日チェックを skip",
    )
    parser.add_argument(
        "--open-download-dir",
        action="store_true",
        help="Download フォルダを Explorer/Finder で開く",
    )
    parser.add_argument(
        "--open-output-dir",
        action="store_true",
        help="出力先フォルダを Explorer/Finder で開く",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実行せずジョブ一覧を表示",
    )
    return parser.parse_args(argv)


# ── main ─────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    setup_logging()

    args = parse_args(argv)

    # --- 営業日判定 ---
    if not args.force:
        should_run, reason = should_run_download()
        if not should_run:
            logger.info("非営業日のため skip (%s)", reason)
            return 0

    # --- setup ---
    try:
        active_jobs = load_active_jobs(
            args.macro_dir, ids_file=args.ids_file, exclude_success=args.retry,
        )
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    if args.dry_run:
        _print_dry_run(args, active_jobs)
        return 0

    chrome_path = Path(args.chrome_path).expanduser().resolve()
    ensure_exists(chrome_path, "Chrome")

    download_dir = resolve_download_dir(args.download_dir)
    ensure_exists(download_dir, "Download directory")

    user_data_dir = _resolve_user_data_dir(args)

    # --- CSV_STAGING_ROOT probe ---
    if not args.direct_deliver:
        if not CSV_STAGING_ROOT.is_dir():
            logger.error("CSV_STAGING_ROOT が存在しません: %s", CSV_STAGING_ROOT)
            return 1
        probe_output_dir(CSV_STAGING_ROOT)

    work_dir: Path | None = None
    if args.direct_deliver:
        output_dir = None
    else:
        work_dir = prepare_work_dir(CSV_STAGING_DIR)
        output_dir = work_dir

    _log_run_config(chrome_path, download_dir, user_data_dir, args, output_dir)

    # --- フォルダを開く ---
    if args.open_download_dir:
        open_folder(download_dir)
    if args.open_output_dir:
        open_folder(output_dir if output_dir else CSV_STAGING_ROOT)

    # --- pre-flight login check ---
    session: BrowserSession | None = None

    if not args.no_login_check:
        try:
            session = prepare_salesforce_session(
                port=args.port,
                chrome_exe=str(chrome_path),
                user_data_dir=str(user_data_dir) if user_data_dir else None,
                url=SF_HOME_URL,
                try_existing=True,
            )
            logger.info("pre-flight login check 完了")
        except Exception:
            logger.exception("pre-flight login check に失敗したため中断します")
            return 1

    driver = session.driver if session else None

    # --- execute ---
    try:
        results = export_batch(
            chrome_path,
            active_jobs,
            download_dir,
            timeout=args.timeout,
            poll=args.poll,
            interval=args.interval,
            date_suffix=args.date_suffix,
            output_dir=output_dir,
            user_data_dir=user_data_dir,
            profile_directory=args.profile_directory,
            driver=driver,
        )

        ok, ng = log_summary(results)
        write_success_ids(results)

        if output_dir is not None:
            write_marker(output_dir, ok, ng)

        if work_dir is not None:
            swap_work_to_staging(work_dir, CSV_STAGING_DIR, ok)

        return 1 if ok < len(results) else 0
    finally:
        # exception 時: work_dir を cleanup、current はそのまま残る
        if work_dir is not None and work_dir.is_dir():
            shutil.rmtree(work_dir, ignore_errors=True)
        if session:
            close_browser_session(session)


if __name__ == "__main__":
    sys.exit(main())
