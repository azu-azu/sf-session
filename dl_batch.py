"""VBA procSalseForce の Python 移植 — バッチ export スクリプト。

ログイン済み Chrome で Salesforce export URL を順次開き、
Downloads フォルダを監視して新規ファイルを移動先にリネーム・コピーする。

Usage:
    python sf-session/dl_batch.py --chrome-path /path/to/chrome --dry-run
    python sf-session/dl_batch.py --chrome-path /path/to/chrome --date-suffix
    python sf-session/dl_batch.py --chrome-path /path/to/chrome --box-folder
    python sf-session/dl_batch.py --chrome-path /path/to/chrome --ids-file
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

from config import CHROME_EXE_PATH, CHROME_USER_DATA_DIR, DEFAULT_IDS_FILE, MACRO_DIR, CSV_STAGING_DIR
from macro_book_reader import JobEntry, load_active_jobs
from utils import setup_logging
from dl_single import (
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
) -> ExportResult:
    """1レポートの export を実行し結果を返す。"""
    report_id = job.report_id or ""
    t0 = time.time()

    # report_id が空なら skip
    if not report_id:
        return ExportResult(
            seq=seq,
            report_id=report_id,
            success=False,
            elapsed=0.0,
            error="report_id が空",
        )

    # encode 列の値を使う（空なら Shift_JIS）
    enc = job.encode if job.encode else "Shift_JIS"
    export_url = build_export_url(report_id, enc=enc)

    # Downloads のベースライン取得
    before = snapshot_files(download_dir, DOWNLOAD_EXTS)

    # Chrome で export URL を開く
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

    # ダウンロード完了を待機
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
        "--box-folder",
        action="store_true",
        help="Box フォルダに per-job 振り分け (default: outputs_csv/ に全出力)",
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
        active_jobs = load_active_jobs(args.macro_dir, ids_file=args.ids_file)
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

    # --- execute ---
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
    )

    log_summary(results)

    failed = sum(1 for r in results if not r.success)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# Tests (run with: cd sf-session && python -m pytest dl_batch.py -v)
# ---------------------------------------------------------------------------


def _make_job(**kwargs) -> JobEntry:
    """テスト用 JobEntry ファクトリ。"""
    defaults = dict(
        no="1",
        report_id="00O123",
        has_filename=False,
        new_filename="",
        src_folder_name="/tmp/dest",
        encode="Shift_JIS",
        skip="",
    )
    defaults.update(kwargs)
    return JobEntry(**defaults)


class TestBuildDestination:
    def test_no_filename_no_suffix(self, tmp_path):
        job = _make_job(src_folder_name=str(tmp_path))
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        result = build_destination(job, downloaded, date_suffix=False)
        assert result == tmp_path / "report.csv"

    def test_with_filename(self, tmp_path):
        job = _make_job(
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="myreport",
        )
        downloaded = tmp_path / "original.csv"
        downloaded.touch()

        result = build_destination(job, downloaded, date_suffix=False)
        assert result == tmp_path / "myreport.csv"

    def test_with_date_suffix(self, tmp_path):
        from unittest.mock import patch

        job = _make_job(src_folder_name=str(tmp_path))
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        with patch("dl_batch.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260317"
            result = build_destination(job, downloaded, date_suffix=True)

        assert result == tmp_path / "report_20260317.csv"

    def test_with_filename_and_date_suffix(self, tmp_path):
        from unittest.mock import patch

        job = _make_job(
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="daily",
        )
        downloaded = tmp_path / "original.xlsx"
        downloaded.touch()

        with patch("dl_batch.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260317"
            result = build_destination(job, downloaded, date_suffix=True)

        assert result == tmp_path / "daily_20260317.xlsx"

    def test_preserves_download_extension(self, tmp_path):
        job = _make_job(
            src_folder_name=str(tmp_path),
            has_filename=True,
            new_filename="output",
        )
        downloaded = tmp_path / "data.xls"
        downloaded.touch()

        result = build_destination(job, downloaded, date_suffix=False)
        assert result == tmp_path / "output.xls"

    def test_output_dir_prefixes_report_id(self, tmp_path):
        out_dir = tmp_path / "outputs_csv"
        out_dir.mkdir()
        job = _make_job(report_id="00O999")
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        result = build_destination(
            job, downloaded, date_suffix=False, output_dir=out_dir,
        )
        assert result == out_dir / "00O999_report.csv"

    def test_output_dir_with_new_filename(self, tmp_path):
        out_dir = tmp_path / "outputs_csv"
        out_dir.mkdir()
        job = _make_job(
            report_id="00O999",
            has_filename=True,
            new_filename="daily",
        )
        downloaded = tmp_path / "original.csv"
        downloaded.touch()

        result = build_destination(
            job, downloaded, date_suffix=False, output_dir=out_dir,
        )
        assert result == out_dir / "00O999_daily.csv"

    def test_output_dir_with_date_suffix(self, tmp_path):
        from unittest.mock import patch

        out_dir = tmp_path / "outputs_csv"
        out_dir.mkdir()
        job = _make_job(report_id="00O999")
        downloaded = tmp_path / "report.csv"
        downloaded.touch()

        with patch("dl_batch.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260318"
            result = build_destination(
                job, downloaded, date_suffix=True, output_dir=out_dir,
            )

        assert result == out_dir / "00O999_report_20260318.csv"


class TestExportOne:
    def test_empty_report_id_returns_failure(self, tmp_path):
        job = _make_job(report_id=None)
        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1)
        assert not result.success
        assert "report_id が空" in result.error

    def test_timeout_returns_failure(self, tmp_path, monkeypatch):
        job = _make_job()

        monkeypatch.setattr(
            "dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "dl_batch.wait_for_new_download",
            lambda *a, **kw: (_ for _ in ()).throw(
                TimeoutError("timeout")
            ),
        )

        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1, timeout=1)
        assert not result.success
        assert "timeout" in result.error

    def test_success(self, tmp_path, monkeypatch):
        job = _make_job()
        downloaded = tmp_path / "report.csv"
        downloaded.write_text("data")

        monkeypatch.setattr(
            "dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1)
        assert result.success
        assert result.dest_path == downloaded

    def test_chrome_launch_failure(self, tmp_path, monkeypatch):
        job = _make_job()

        monkeypatch.setattr(
            "dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "dl_batch.subprocess.Popen",
            lambda cmd: (_ for _ in ()).throw(OSError("not found")),
        )

        result = export_one(Path("/dummy/chrome"), job, tmp_path, seq=1)
        assert not result.success
        assert "Chrome 起動失敗" in result.error

    def test_user_data_dir_passed_to_chrome(self, tmp_path, monkeypatch):
        job = _make_job()
        downloaded = tmp_path / "report.csv"
        downloaded.write_text("data")

        launched_cmds: list[list[str]] = []
        monkeypatch.setattr(
            "dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "dl_batch.subprocess.Popen",
            lambda cmd: launched_cmds.append(cmd),
        )
        monkeypatch.setattr(
            "dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        udd = tmp_path / "ChromeProfile"
        result = export_one(
            Path("/dummy/chrome"), job, tmp_path,
            seq=1, user_data_dir=udd, profile_directory="Profile 1",
        )
        assert result.success
        cmd = launched_cmds[0]
        assert f"--user-data-dir={udd}" in cmd
        assert "--profile-directory=Profile 1" in cmd


class TestExportBatch:
    def test_skip_filtered_by_caller(self, tmp_path, monkeypatch):
        """skip フィルタは呼び出し側の責務。active_jobs のみ渡す。"""
        all_jobs = [
            _make_job(no="1", skip="x"),
            _make_job(no="2", skip=""),
        ]
        active_jobs = [j for j in all_jobs if not j.skip]

        downloaded = tmp_path / "report.csv"
        downloaded.write_text("data")

        monkeypatch.setattr(
            "dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        results = export_batch(
            Path("/dummy/chrome"), active_jobs, tmp_path, interval=0
        )
        assert len(results) == 1
        assert results[0].seq == 1

    def test_failure_continues(self, tmp_path, monkeypatch):
        """1件目が失敗しても2件目は実行される。"""
        call_count = {"n": 0}

        def mock_wait(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise TimeoutError("timeout")
            downloaded = tmp_path / "report2.csv"
            downloaded.write_text("data2")
            return downloaded

        jobs = [
            _make_job(no="1"),
            _make_job(no="2"),
        ]

        monkeypatch.setattr(
            "dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "dl_batch.wait_for_new_download", mock_wait
        )

        results = export_batch(
            Path("/dummy/chrome"), jobs, tmp_path, interval=0
        )
        assert len(results) == 2
        assert not results[0].success
        assert results[1].success

    def test_move_to_dest_dir(self, tmp_path, monkeypatch):
        """成功時にファイルが dest_dir に移動される。"""
        dest_dir = tmp_path / "output"
        dest_dir.mkdir()

        downloaded = tmp_path / "dl" / "report.csv"
        downloaded.parent.mkdir()
        downloaded.write_text("data")

        job = _make_job(no="1", src_folder_name=str(dest_dir))

        monkeypatch.setattr(
            "dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        results = export_batch(
            Path("/dummy/chrome"), [job], tmp_path / "dl", interval=0
        )
        assert len(results) == 1
        assert results[0].success
        assert results[0].dest_path == dest_dir / "report.csv"
        assert (dest_dir / "report.csv").exists()

    def test_output_dir_moves_files(self, tmp_path, monkeypatch):
        """output_dir 指定時、output_dir に report_id prefix で移動。"""
        out_dir = tmp_path / "outputs_csv"
        out_dir.mkdir()

        downloaded = tmp_path / "dl" / "report.csv"
        downloaded.parent.mkdir()
        downloaded.write_text("data")

        job = _make_job(no="1", report_id="00O999")

        monkeypatch.setattr(
            "dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        results = export_batch(
            Path("/dummy/chrome"), [job], tmp_path / "dl",
            interval=0, output_dir=out_dir,
        )
        assert len(results) == 1
        assert results[0].success
        assert results[0].dest_path == out_dir / "00O999_report.csv"
        assert (out_dir / "00O999_report.csv").exists()

    def test_dest_dir_missing_stays_in_downloads(self, tmp_path, monkeypatch):
        """移動先フォルダが存在しない場合、Downloads に残る。"""
        downloaded = tmp_path / "report.csv"
        downloaded.write_text("data")

        job = _make_job(
            no="1", src_folder_name=str(tmp_path / "nonexistent")
        )

        monkeypatch.setattr(
            "dl_batch.snapshot_files", lambda *a, **kw: {}
        )
        monkeypatch.setattr(
            "dl_batch.subprocess.Popen", lambda cmd: None
        )
        monkeypatch.setattr(
            "dl_batch.wait_for_new_download",
            lambda *a, **kw: downloaded,
        )

        results = export_batch(
            Path("/dummy/chrome"), [job], tmp_path, interval=0
        )
        assert len(results) == 1
        assert results[0].success
        # 移動できず Downloads のまま
        assert results[0].dest_path == downloaded


class TestLogSummary:
    def test_no_error(self, caplog):
        results = [
            ExportResult(
                seq=1, report_id="00O1", success=True,
                elapsed=1.5, dest_path=Path("/out/r.csv"),
            ),
        ]
        with caplog.at_level(logging.INFO):
            log_summary(results)
        assert "成功 1 件" in caplog.text

    def test_with_failures(self, caplog):
        results = [
            ExportResult(
                seq=1, report_id="00O1", success=True,
                elapsed=1.5, dest_path=Path("/out/r.csv"),
            ),
            ExportResult(
                seq=2, report_id="00O2", success=False,
                elapsed=10.0, error="timeout",
            ),
        ]
        with caplog.at_level(logging.INFO):
            log_summary(results)
        assert "成功 1 件" in caplog.text
        assert "失敗 1 件" in caplog.text


class TestParseArgs:
    def test_override_chrome_path(self):
        args = parse_args(["--chrome-path", "/usr/bin/chrome"])
        assert args.chrome_path == "/usr/bin/chrome"

    def test_default_chrome_path(self):
        args = parse_args([])
        assert args.chrome_path == CHROME_EXE_PATH

    def test_defaults(self):
        args = parse_args([])
        assert args.timeout == DEFAULT_TIMEOUT
        assert args.poll == DEFAULT_POLL
        assert args.interval == DEFAULT_INTERVAL
        assert not args.date_suffix
        assert not args.dry_run
        assert not args.box_folder
        assert not args.my_chrome
        assert not args.ids_file
        assert args.user_data_dir == CHROME_USER_DATA_DIR
        assert args.profile_directory is None

    def test_all_flags(self):
        args = parse_args([
            "--chrome-path", "chrome",
            "--download-dir", "/tmp/dl",
            "--timeout", "30",
            "--poll", "0.5",
            "--date-suffix",
            "--interval", "5.0",
            "--box-folder",
            "--ids-file",
            "--dry-run",
            "--my-chrome",
            "--user-data-dir", CHROME_USER_DATA_DIR,
            "--profile-directory", "Profile 1",
        ])
        assert args.download_dir == "/tmp/dl"
        assert args.timeout == 30
        assert args.poll == 0.5
        assert args.date_suffix
        assert args.interval == 5.0
        assert args.box_folder
        assert args.ids_file
        assert args.dry_run
        assert args.my_chrome
        assert args.user_data_dir == CHROME_USER_DATA_DIR
        assert args.profile_directory == "Profile 1"



