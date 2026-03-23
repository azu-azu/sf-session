"""VBA procSalseForce の Python 移植 — バッチ export スクリプト。

ログイン済み Chrome で Salesforce export URL を順次開き、
Downloads フォルダを監視して新規ファイルを移動先にリネーム・コピーする。

Usage:
    python -m sf_session.dl_batch --dry-run
    python -m sf_session.dl_batch --ids-file
    python -m sf_session.dl_batch --retry
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver

from .config import (
    CHROME_EXE_PATH,
    CHROME_USER_DATA_DIR,
    CSV_STAGING_DIR,
    DEFAULT_IDS_FILE,
    MACRO_DIR,
    OUTPUT_RESULTS_DIR,
    SF_HOME_URL,
)
from .browser import (
    REMOTE_DEBUGGING_PORT,
    connect_driver,
    launch_chrome,
    try_connect_driver,
    wait_page_load,
)
from .login_helper import (
    LoginExhaustedError,
    ensure_logged_in,
    find_login_tab,
)
from .macro_book_reader import JobEntry, load_active_jobs
from .utils import setup_logging
from ._dl_single import (
    DOWNLOAD_EXTS,
    build_chrome_command,
    build_export_url,
    ensure_exists,
    resolve_download_dir,
    snapshot_files,
    wait_for_new_download,
)

logger = logging.getLogger(__name__)


# ── 設定値 ──────────────────────────────────────────────
DEFAULT_TIMEOUT = 600  # per-report seconds
DEFAULT_POLL = 2.0  # poll interval seconds
DEFAULT_INTERVAL = 2.0  # inter-report wait seconds
CHROME_STARTUP_WAIT = 5  # seconds


@dataclass
class ExportResult:
    """1レポートの export 結果。"""

    seq: int
    report_id: str
    success: bool
    elapsed: float = 0.0
    dest_path: Path | None = None
    error: str = ""


def build_destination(
    job: JobEntry,
    downloaded: Path,
    *,
    date_suffix: bool,
    output_dir: Path | None = None,
) -> Path:
    """ダウンロードファイルの移動先パスを組み立てる。

    output_dir が指定されていれば全ファイルをそこに出力し、
    ファイル名の先頭に report_id を付与する。
    未指定なら従来通り job.src_folder_name を使う。
    """
    dest_dir = output_dir if output_dir else Path(job.src_folder_name)
    ext = downloaded.suffix
    stem = job.new_filename if job.has_filename else downloaded.stem

    if output_dir and job.report_id:
        stem = f"{job.report_id}_{stem}"

    if date_suffix:
        today = datetime.now().strftime("%Y%m%d")
        stem = f"{stem}_{today}"

    return dest_dir / f"{stem}{ext}"


def _run_export(
    chrome_path: Path,
    job: JobEntry,
    download_dir: Path,
    *,
    seq: int,
    timeout: int,
    poll: float,
    user_data_dir: Path | None,
    profile_directory: str | None,
) -> ExportResult:
    """1レポートの Chrome 起動 → ダウンロード待機。login recovery なしの内部実装。"""
    report_id = job.report_id or ""
    t0 = time.time()

    enc = job.encode if job.encode else "Shift_JIS"
    export_url = build_export_url(report_id, enc=enc)

    before = snapshot_files(download_dir, DOWNLOAD_EXTS)

    cmd = build_chrome_command(
        chrome_path,
        export_url,
        user_data_dir=user_data_dir,
        profile_directory=profile_directory,
        new_window=False,
    )
    logger.info("[%d件目] Chrome を起動: %s", seq, export_url)

    try:
        subprocess.Popen(cmd)
    except OSError as e:
        return ExportResult(
            seq=seq,
            report_id=report_id,
            success=False,
            elapsed=time.time() - t0,
            error=f"Chrome 起動失敗: {e}",
        )

    try:
        downloaded = wait_for_new_download(
            download_dir,
            before,
            timeout_seconds=timeout,
            poll_seconds=poll,
            exts=DOWNLOAD_EXTS,
        )
    except TimeoutError as e:
        return ExportResult(
            seq=seq,
            report_id=report_id,
            success=False,
            elapsed=time.time() - t0,
            error=str(e),
        )

    elapsed = time.time() - t0
    logger.info("[%d件目] ダウンロード検知: %s (%.1fs)", seq, downloaded.name, elapsed)

    return ExportResult(
        seq=seq,
        report_id=report_id,
        success=True,
        elapsed=elapsed,
        dest_path=downloaded,
    )


def export_one(
    chrome_path: Path,
    job: JobEntry,
    download_dir: Path,
    *,
    seq: int,
    timeout: int = DEFAULT_TIMEOUT,
    poll: float = DEFAULT_POLL,
    user_data_dir: Path | None = None,
    profile_directory: str | None = None,
    driver: WebDriver | None = None,
) -> ExportResult:
    """1レポートの export を実行し結果を返す。

    driver が渡されている場合、timeout 後にタブ traverse で
    ログイン/SSO ページを検出し、手動ログイン待機 → 1回だけリトライする。
    """
    report_id = job.report_id or ""

    if not report_id:
        return ExportResult(
            seq=seq,
            report_id=report_id,
            success=False,
            elapsed=0.0,
            error="report_id が空",
        )

    result = _run_export(
        chrome_path, job, download_dir,
        seq=seq, timeout=timeout, poll=poll,
        user_data_dir=user_data_dir, profile_directory=profile_directory,
    )

    # timeout 失敗 + driver あり → login recovery を試行（1回限り）
    if not result.success and driver is not None:
        if find_login_tab(driver):
            logger.info("[%d件目] ログインページ検出 — login recovery 開始", seq)
            try:
                ensure_logged_in(driver)
            except LoginExhaustedError as e:
                logger.warning("[%d件目] login recovery 失敗: %s", seq, e)
                result.error = f"login recovery 失敗: {e}"
                return result
            logger.info("[%d件目] login recovery 完了 — リトライ", seq)
            result = _run_export(
                chrome_path, job, download_dir,
                seq=seq, timeout=timeout, poll=poll,
                user_data_dir=user_data_dir, profile_directory=profile_directory,
            )
        else:
            logger.debug("[%d件目] ログインページ未検出 — recovery skip", seq)

    return result


def export_batch(
    chrome_path: Path,
    jobs: list[JobEntry],
    download_dir: Path,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    poll: float = DEFAULT_POLL,
    interval: float = DEFAULT_INTERVAL,
    date_suffix: bool = False,
    output_dir: Path | None = None,
    user_data_dir: Path | None = None,
    profile_directory: str | None = None,
    driver: WebDriver | None = None,
) -> list[ExportResult]:
    """ジョブリストを順次 export し、結果リストを返す。"""
    results: list[ExportResult] = []

    for i, job in enumerate(jobs):
        seq = i + 1
        result = export_one(
            chrome_path, job, download_dir,
            seq=seq, timeout=timeout, poll=poll,
            user_data_dir=user_data_dir,
            profile_directory=profile_directory,
            driver=driver,
        )

        if not result.success or result.dest_path is None:
            results.append(result)
            continue

        # 移動先を組み立て
        dest = build_destination(
            job, result.dest_path,
            date_suffix=date_suffix,
            output_dir=output_dir,
        )
        dest_dir = dest.parent

        if not dest_dir.is_dir():
            logger.warning(
                "[%d件目] 移動先フォルダが存在しません: %s。Downloads に残します。",
                seq, dest_dir,
            )
        else:
            try:
                shutil.move(str(result.dest_path), str(dest))
                logger.info("[%d件目] 移動完了: %s", seq, dest)
                result.dest_path = dest
            except OSError as e:
                logger.error("[%d件目] 移動失敗: %s", seq, e)
                result.success = False
                result.error = f"ファイル移動失敗: {e}"

        results.append(result)

        # 最後のジョブでなければ interval だけ待機
        if i < len(jobs) - 1 and interval > 0:
            time.sleep(interval)

    return results


def log_summary(results: list[ExportResult]) -> None:
    """実行結果のサマリーをログ出力する。"""
    ok = sum(1 for r in results if r.success)
    ng = sum(1 for r in results if not r.success)

    logger.info("*" * 50)
    logger.info("sf_dl_batch complete >>")
    logger.info("成功 %d 件 / 失敗 %d 件 / 合計 %d 件", ok, ng, len(results))
    logger.info("-" * 50)

    for r in results:
        status = "OK" if r.success else "NG"
        dest = r.dest_path or "-"
        err = f" ({r.error})" if r.error else ""
        logger.info(
            "  [%s] %d件目 %s  %.1fs  %s%s",
            status, r.seq, r.report_id, r.elapsed, dest, err,
        )

    logger.info("*" * 50)


def write_success_ids(results: list[ExportResult]) -> Path | None:
    """成功した report_id を OUTPUT_RESULTS_DIR/success_ids_YYYYMMDD.txt に書き出す。"""
    ids = [r.report_id for r in results if r.success and r.report_id]
    if not ids:
        return None

    OUTPUT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    path = OUTPUT_RESULTS_DIR / f"success_ids_{today}.txt"
    path.write_text("\n".join(ids) + "\n", encoding="utf-8")
    logger.info("success_ids を書き出し: %s (%d 件)", path.name, len(ids))
    return path


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
        "--box-folder",
        action="store_true",
        help="Box フォルダに per-job 振り分け (default: outputs_csv/ に全出力)",
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
        "--dry-run",
        action="store_true",
        help="実行せずジョブ一覧を表示",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()

    args = parse_args(argv)

    # --- setup ---
    try:
        active_jobs = load_active_jobs(
            args.macro_dir, ids_file=args.ids_file, exclude_success=args.retry,
        )
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    if args.dry_run:
        if not args.box_folder:
            logger.info("Output dir  : %s", CSV_STAGING_DIR)
        logger.info("--- dry-run mode ---")
        dummy_dl = Path("{download}")
        for i, j in enumerate(active_jobs, 1):
            rid = j.report_id or "(なし)"
            enc = j.encode if j.encode else "Shift_JIS"
            url = build_export_url(rid, enc=enc) if j.report_id else "(URL 構築不可)"
            if not args.box_folder:
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
        return 0

    chrome_path = Path(args.chrome_path).expanduser().resolve()
    ensure_exists(chrome_path, "Chrome")

    download_dir = resolve_download_dir(args.download_dir)
    ensure_exists(download_dir, "Download directory")

    if args.my_chrome:
        if args.user_data_dir != CHROME_USER_DATA_DIR:
            logger.warning("--my-chrome が指定されたため --user-data-dir は無視されます")
        user_data_dir = None
    else:
        user_data_dir = (
            Path(args.user_data_dir).expanduser().resolve()
            if args.user_data_dir
            else None
        )
        if user_data_dir is not None:
            ensure_exists(user_data_dir, "Chrome user data dir")

    if args.box_folder:
        output_dir = None
    else:
        output_dir = CSV_STAGING_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        # 既存ファイルを全削除（サブフォルダは残す）
        removed = [f for f in output_dir.iterdir() if f.is_file()]
        for f in removed:
            f.unlink()
        if removed:
            logger.info("既存 %d 件を削除: %s", len(removed), output_dir)

    logger.info("Chrome      : %s", chrome_path)
    logger.info("Downloads   : %s", download_dir)
    if user_data_dir is not None:
        logger.info("UserDataDir : %s", user_data_dir)
    if args.profile_directory:
        logger.info("Profile     : %s", args.profile_directory)
    logger.info("Timeout     : %ds", args.timeout)
    logger.info("date-suffix : %s", args.date_suffix)
    if output_dir:
        logger.info("Output dir  : %s", output_dir)
    else:
        logger.info("Output mode : box-folder (per-job)")

    # --- pre-flight login check ---
    driver = None
    chrome_proc = None

    if not args.no_login_check:
        from selenium.common.exceptions import WebDriverException

        driver = try_connect_driver(port=args.port)

        # 既存 Chrome に接続できなければ自前で起動
        if driver is None and user_data_dir is not None:
            try:
                chrome_proc = launch_chrome(
                    exe=str(chrome_path), port=args.port,
                    user_data_dir=str(user_data_dir),
                )
                time.sleep(CHROME_STARTUP_WAIT)
                driver = connect_driver(port=args.port)
            except (OSError, WebDriverException, ImportError) as e:
                logger.warning("Chrome 起動/接続失敗: %s — login check skip", e)
                driver = None

        if driver is not None:
            try:
                driver.get(SF_HOME_URL)
                wait_page_load(driver)
                ensure_logged_in(driver)
                logger.info("pre-flight login check 完了")
            # TimeoutError は MfaTimeoutError (subclass) も含む
            except (WebDriverException, TimeoutError, LoginExhaustedError) as e:
                logger.warning("pre-flight login check 失敗: %s — export を続行", e)
                driver = None
        else:
            logger.info("WebDriver 接続不可 — login check skip")

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

        log_summary(results)
        write_success_ids(results)

        if output_dir is not None:
            ok = sum(1 for r in results if r.success)
            ng = sum(1 for r in results if not r.success)
            marker = output_dir / f"★完了_成功{ok}件_失敗{ng}件.txt"
            marker.touch()
            logger.info("完了マーカー: %s", marker.name)

        failed = sum(1 for r in results if not r.success)
        return 1 if failed else 0
    finally:
        if chrome_proc and chrome_proc.poll() is None:
            logger.info("Chrome プロセス終了 (PID=%d)", chrome_proc.pid)
            chrome_proc.terminate()
            chrome_proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
