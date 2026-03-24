"""download のレポート export 実行エンジン。

ExportResult dataclass と、export_one / export_batch を提供する。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver

from .login_helper import (
    LoginExhaustedError,
    ensure_logged_in,
    find_login_tab,
)
from .macro_book_reader import JobEntry
from ._download_single import (
    DOWNLOAD_EXTS,
    build_chrome_command,
    build_export_url,
    snapshot_files,
    wait_for_new_download,
)
from .download_outputs import build_destination

logger = logging.getLogger(__name__)

# ── 設定値 ──────────────────────────────────────────────
DEFAULT_TIMEOUT = 600  # per-report seconds
DEFAULT_POLL = 2.0  # poll interval seconds
DEFAULT_INTERVAL = 2.0  # inter-report wait seconds


@dataclass
class ExportResult:
    """1レポートの export 結果。"""

    seq: int
    report_id: str
    success: bool
    elapsed: float = 0.0
    dest_path: Path | None = None
    error: str = ""


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
