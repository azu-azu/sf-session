"""VBA procSalseForce の Python 移植 — バッチ export スクリプト。

ログイン済み Chrome で Salesforce export URL を順次開き、
Downloads フォルダを監視して新規ファイルを移動先にリネーム・コピーする。

Usage:
    python -m sf_session.download archive --dry-run
    python -m sf_session.download archive --ids-file
    python -m sf_session.download archive --retry
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
from pathlib import Path

from ..config import (
    CHROME_EXE_PATH,
    CHROME_USER_DATA_DIR,
    PIPELINES,
    SF_HOME_URL,
    VALID_PIPELINES,
    OUTPUT_ROOT,
)
from ..browser import REMOTE_DEBUGGING_PORT
from ..business_day import should_run_download
from ..macro_book_reader import JobEntry, load_active_jobs
from ..pipeline_status import write_pipeline_status
from ..utils import setup_logging, short_path, time_label
from .single import (
    build_export_url,
    ensure_exists,
    resolve_download_dir,
)
from .runner import (
    DEFAULT_TIMEOUT,
    DEFAULT_POLL,
    DEFAULT_INTERVAL,
    export_batch,
)
from .outputs import (
    build_destination,
    log_summary,
    open_folder,
    prepare_work_dir,
    probe_destinations,
    probe_output_dir,
    swap_work_to_staging,
    write_completion_marker,
    write_start_marker,
    write_success_ids,
)
from ..session import (
    BrowserSession,
    close_browser_session,
    prepare_salesforce_session,
)

logger = logging.getLogger(__name__)


# ── config ──────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class RunConfig:
    """parse 後に resolve 済みの実行設定。"""

    chrome_path: Path
    download_dir: Path
    user_data_dir: Path | None
    profile_directory: str | None
    port: int
    pipeline: str
    timeout: int
    poll: float
    interval: float
    direct_deliver: bool
    mkdir: bool
    open_download_dir: bool
    open_output_dir: bool


# ── internal helpers ─────────────────────────────────────


def _resolve_user_data_dir(my_chrome: bool, raw_user_data_dir: str) -> Path | None:
    """--my-chrome 処理を含む user_data_dir 解決。"""
    if my_chrome:
        if raw_user_data_dir != CHROME_USER_DATA_DIR:
            logger.warning("--my-chrome が指定されたため --user-data-dir は無視されます")
        return None

    if not raw_user_data_dir:
        return None

    resolved = Path(raw_user_data_dir).expanduser().resolve()
    ensure_exists(resolved, "Chrome user data dir")
    return resolved


def _log_run_config(cfg: RunConfig, output_dir: Path | None) -> None:
    """設定値をログ出力。"""
    logger.info("Chrome      : %s", cfg.chrome_path)
    logger.info("Downloads   : %s", cfg.download_dir)
    if cfg.user_data_dir is not None:
        logger.info("UserDataDir : %s", cfg.user_data_dir)
    if cfg.profile_directory:
        logger.info("Profile     : %s", cfg.profile_directory)
    logger.info("Port        : %d", cfg.port)
    logger.info("Timeout     : %ds", cfg.timeout)
    if output_dir:
        logger.info("Output dir  : %s", short_path(output_dir))
    else:
        logger.info("Output mode : direct-deliver (per-job)")


def _print_dry_run(direct_deliver: bool, jobs, *, csv_dir: Path) -> None:
    """dry-run モードのジョブ一覧表示。"""
    if not direct_deliver:
        logger.info("Output dir  : %s", short_path(csv_dir))
    logger.info("--- dry-run mode ---")
    dummy_dl = Path("{download}")
    for i, j in enumerate(jobs, 1):
        rid = j.report_id or "(なし)"
        enc = j.encode if j.encode else "Shift_JIS"
        url = build_export_url(rid, enc=enc) if j.report_id else "(URL 構築不可)"
        if not direct_deliver:
            dest = build_destination(
                j, dummy_dl,
                mode="download", output_dir=csv_dir,
            )
        else:
            dest = build_destination(
                j, dummy_dl,
                mode="download_direct",
            )
        logger.info(
            "  [%d件目] %s  enc=%s  → %s  %s",
            i, rid, enc, short_path(dest), url,
        )


# ── CLI ──────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VBA procSalseForce 相当 — バッチ export スクリプト",
    )
    parser.add_argument(
        "pipeline",
        choices=VALID_PIPELINES,
        help="実行対象の pipeline 名",
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
        help="普段使いの Chrome で実行 (keeper の専用プロファイルではなく OS デフォルト)",
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
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"レポート間 wait 秒 (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--macro-dir",
        type=Path,
        default=None,
        help="マクロ格納フォルダ path (default: pipeline config)",
    )
    parser.add_argument(
        "--ids-file",
        action="store_true",
        default=False,
        help="ids.txt から report ID を読み取り、ジョブ定義との intersection でフィルタ",
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
        help="per-job 振り分け先フォルダへ直接コピー (default: pipeline の csv_dir に全出力)",
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
        "--mkdir",
        action="store_true",
        help="移動先フォルダが存在しない場合、親があれば最終フォルダを自動作成",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実行せずジョブ一覧を表示",
    )
    return parser.parse_args(argv)


# ── main ─────────────────────────────────────────────────


def _prepare_session(cfg: RunConfig) -> BrowserSession:
    """pre-flight login check。失敗時は例外を raise。"""
    session = prepare_salesforce_session(
        port=cfg.port,
        chrome_exe=str(cfg.chrome_path),
        user_data_dir=str(cfg.user_data_dir) if cfg.user_data_dir else None,
        url=SF_HOME_URL,
        try_existing=True,
    )
    logger.info("pre-flight login check 完了")
    return session


def _finalize(
    results: list,
    *,
    pipeline: str,
    phase: str,
    work_dir: Path | None,
    csv_dir: Path,
    result_dir: Path,
) -> int:
    """結果出力 + swap + status marker。return code を返す。"""
    ok, ng = log_summary(results)
    write_success_ids(results, result_dir=result_dir)

    if work_dir is not None:
        write_completion_marker(work_dir, ok, ng)
        swap_work_to_staging(work_dir, csv_dir, ok)

    other = "dl" if phase == "direct" else "direct"
    write_pipeline_status(
        OUTPUT_ROOT.parent, pipeline, phase,
        f"{time_label()}_成功{ok}件_失敗{ng}件",
        clear_phases=[other, "dv"],
    )

    return 1 if ok < len(results) else 0


def _execute(
    cfg: RunConfig,
    active_jobs: list[JobEntry],
    session: BrowserSession | None,
    *,
    csv_dir: Path,
    result_dir: Path,
) -> int:
    """Chrome 起動 → export → finalize。"""
    assert OUTPUT_ROOT is not None  # validated by _load_pipelines
    driver = session.driver if session else None
    work_dir: Path | None = None

    try:
        if cfg.direct_deliver:
            errors = probe_destinations(active_jobs, mkdir=cfg.mkdir)
            if errors:
                for msg in errors:
                    logger.error("移動先フォルダに問題があります: %s", msg)
                return 1
        else:
            if not OUTPUT_ROOT.parent.is_dir():
                logger.error("OUTPUT_ROOT の親ディレクトリが存在しません: %s", OUTPUT_ROOT.parent)
                return 1
            probe_output_dir(OUTPUT_ROOT.parent)
            OUTPUT_ROOT.mkdir(exist_ok=True)

        # direct_deliver: 各 job の振り分け先へ直接コピー
        # それ以外: work_dir に一旦 export し、完了後に csv_dir へ atomic swap
        #           → 途中 crash しても csv_dir が中途半端な状態にならない
        if cfg.direct_deliver:
            output_dir = None
        else:
            work_dir = prepare_work_dir(csv_dir)
            output_dir = work_dir

        _log_run_config(cfg, output_dir)

        if cfg.open_download_dir:
            open_folder(cfg.download_dir)
        if cfg.open_output_dir:
            open_folder(output_dir if output_dir else OUTPUT_ROOT.parent)

        if output_dir is not None:
            write_start_marker(output_dir, len(active_jobs))

        phase = "direct" if cfg.direct_deliver else "dl"
        write_pipeline_status(
            OUTPUT_ROOT.parent, cfg.pipeline, phase,
            f"START_{time_label()}_{len(active_jobs)}件の予定",
        )

        mode = "download_direct" if cfg.direct_deliver else "download"
        results = export_batch(
            cfg.chrome_path,
            active_jobs,
            cfg.download_dir,
            mode=mode,
            timeout=cfg.timeout,
            poll=cfg.poll,
            interval=cfg.interval,
            output_dir=output_dir,
            user_data_dir=cfg.user_data_dir,
            profile_directory=cfg.profile_directory,
            driver=driver,
        )

        return _finalize(
            results,
            pipeline=cfg.pipeline, phase=phase,
            work_dir=work_dir, csv_dir=csv_dir, result_dir=result_dir,
        )
    except KeyboardInterrupt:
        logger.info("Ctrl-C で中断")
        return 130
    finally:
        if work_dir is not None and work_dir.is_dir():
            logger.info("中断のため work_dir を保持: %s", work_dir.name)
        if session:
            close_browser_session(session)


def main(argv: list[str] | None = None) -> int:
    setup_logging()

    args = parse_args(argv)
    pipeline = PIPELINES[args.pipeline]

    # --- 営業日判定 ---
    if not args.force:
        should_run, reason = should_run_download()
        if not should_run:
            logger.info("非営業日のため skip (%s)", reason)
            return 0

    # --- setup ---
    try:
        effective = dataclasses.replace(pipeline, macro_dir=args.macro_dir) if args.macro_dir else pipeline
        active_jobs = load_active_jobs(
            effective, ids_file=args.ids_file, exclude_success=args.retry,
        )
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    if not active_jobs:
        logger.info("実行対象のジョブが 0 件のため終了します")
        return 0

    if args.dry_run:
        _print_dry_run(args.direct_deliver, active_jobs, csv_dir=pipeline.csv_dir)
        return 0

    # --- resolve paths ---
    chrome_path = Path(args.chrome_path).expanduser().resolve()
    ensure_exists(chrome_path, "Chrome")

    download_dir = resolve_download_dir(args.download_dir)
    ensure_exists(download_dir, "Download directory")

    user_data_dir = _resolve_user_data_dir(args.my_chrome, args.user_data_dir)

    cfg = RunConfig(
        chrome_path=chrome_path,
        download_dir=download_dir,
        user_data_dir=user_data_dir,
        profile_directory=args.profile_directory,
        port=args.port,
        pipeline=args.pipeline,
        timeout=args.timeout,
        poll=args.poll,
        interval=args.interval,
        direct_deliver=args.direct_deliver,
        mkdir=args.mkdir,
        open_download_dir=args.open_download_dir,
        open_output_dir=args.open_output_dir,
    )

    # --- pre-flight login ---
    session = None
    if not args.no_login_check:
        try:
            session = _prepare_session(cfg)
        except Exception:  # Chrome + Selenium + SF login — 例外が多岐にわたるため broad catch
            logger.exception("pre-flight login check に失敗したため中断します")
            return 1

    # --- execute ---
    return _execute(
        cfg, active_jobs, session,
        csv_dir=pipeline.csv_dir, result_dir=pipeline.result_dir,
    )
