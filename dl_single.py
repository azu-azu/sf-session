"""PoC: VBA と同じ方式で Salesforce レポート export を試す。

方式:
- requests で sid を付けて直叩きしない
- ログイン済み Chrome で export URL を開く
- Downloads フォルダに新規作成された csv/xls/xlsx を監視
- 見つけたファイルを必要なら移動/リネームする

前提:
- Chrome 側ですでに Salesforce にログイン済みであること
- 可能なら専用の Chrome プロファイルを使うこと
- 初回は手動で同じプロファイルの Chrome から Salesforce にログインしておくこと
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

from config import SF_BASE_URL

logger = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────
DOWNLOAD_EXTS = {".csv", ".xls", ".xlsx"}
DOWNLOAD_TIMEOUT = 120  # seconds
POLL_INTERVAL = 2.0  # seconds


def build_export_url(report_id: str, enc: str = "UTF-8", fmt: str = "csv") -> str:
    return f"{SF_BASE_URL}/{report_id}?isdtp=p1&export=1&enc={enc}&xf={fmt}"


def snapshot_files(directory: Path, exts: set[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() in exts:
            result[path.name] = path.stat().st_mtime
    return result


def is_temporary_download(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.endswith(".crdownload")
        or name.endswith(".tmp")
        or name.endswith(".part")
    )


def wait_for_new_download(
    download_dir: Path,
    before: dict[str, float],
    *,
    timeout_seconds: int,
    poll_seconds: float,
    exts: set[str],
) -> Path:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        current_candidates: list[Path] = []

        for path in download_dir.iterdir():
            if not path.is_file():
                continue
            if is_temporary_download(path):
                continue
            if path.suffix.lower() not in exts:
                continue

            mtime = path.stat().st_mtime
            old_mtime = before.get(path.name)

            if old_mtime is None or mtime > old_mtime:
                current_candidates.append(path)

        if current_candidates:
            current_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            newest = current_candidates[0]

            size1 = newest.stat().st_size
            time.sleep(max(poll_seconds, 1.0))
            if newest.exists():
                size2 = newest.stat().st_size
                if size1 == size2:
                    return newest

        time.sleep(poll_seconds)

    raise TimeoutError(
        f"{timeout_seconds} 秒以内に新しいダウンロードファイルを検知できませんでした。"
    )


def resolve_download_dir(download_dir_arg: str | None) -> Path:
    if download_dir_arg:
        return Path(download_dir_arg).expanduser().resolve()
    return (Path.home() / "Downloads").resolve()


def ensure_exists(path: Path, kind: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{kind} が存在しません: {path}")


def build_chrome_command(
    chrome_path: Path,
    url: str,
    *,
    user_data_dir: Path | None,
    profile_directory: str | None,
    new_window: bool,
) -> list[str]:
    cmd = [str(chrome_path)]

    if user_data_dir is not None:
        cmd.append(f"--user-data-dir={user_data_dir}")

    if profile_directory:
        cmd.append(f"--profile-directory={profile_directory}")

    if new_window:
        cmd.append("--new-window")

    cmd.append(url)
    return cmd


def move_or_copy_file(
    src: Path,
    *,
    output: Path | None,
    keep_original: bool,
) -> Path:
    if output is None:
        return src

    output.parent.mkdir(parents=True, exist_ok=True)

    if keep_original:
        shutil.copy2(src, output)
    else:
        shutil.move(str(src), str(output))

    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open Salesforce export URL in logged-in Chrome and watch Downloads."
    )
    parser.add_argument("report_id", help="Salesforce report ID (e.g. 00O...)")
    parser.add_argument("--enc", default="UTF-8", help="Encoding for export URL")
    parser.add_argument("--fmt", default="csv", help="Format: csv or xls")
    parser.add_argument(
        "--chrome-path",
        required=True,
        help='Path to chrome.exe, e.g. "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"',
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Download directory to watch (default: ~/Downloads)",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Chrome user data dir. Use this when you need a specific logged-in Chrome profile.",
    )
    parser.add_argument(
        "--profile-directory",
        default=None,
        help='Chrome profile directory name, e.g. "Default" or "Profile 1"',
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DOWNLOAD_TIMEOUT,
        help=f"Timeout seconds for waiting download (default: {DOWNLOAD_TIMEOUT})",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=POLL_INTERVAL,
        help=f"Polling interval seconds (default: {POLL_INTERVAL})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Destination file path. If omitted, downloaded file stays in Downloads.",
    )
    parser.add_argument(
        "--keep-original",
        action="store_true",
        help="Copy to output instead of move",
    )
    parser.add_argument(
        "--new-window",
        action="store_true",
        help="Open in a new Chrome window",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args(argv)

    chrome_path = Path(args.chrome_path).expanduser().resolve()
    ensure_exists(chrome_path, "Chrome")
    download_dir = resolve_download_dir(args.download_dir)
    ensure_exists(download_dir, "Download directory")

    user_data_dir = (
        Path(args.user_data_dir).expanduser().resolve()
        if args.user_data_dir
        else None
    )
    if user_data_dir is not None:
        ensure_exists(user_data_dir, "Chrome user data dir")

    export_url = build_export_url(args.report_id, enc=args.enc, fmt=args.fmt)

    logger.info("Chrome      : %s", chrome_path)
    logger.info("Downloads   : %s", download_dir)
    if user_data_dir is not None:
        logger.info("UserDataDir : %s", user_data_dir)
    if args.profile_directory:
        logger.info("Profile     : %s", args.profile_directory)
    logger.info("Export URL  : %s", export_url)

    before = snapshot_files(download_dir, DOWNLOAD_EXTS)

    cmd = build_chrome_command(
        chrome_path,
        export_url,
        user_data_dir=user_data_dir,
        profile_directory=args.profile_directory,
        new_window=args.new_window,
    )

    cmd_str = " ".join(f'"{x}"' if " " in x else x for x in cmd)
    logger.info("Launch Chrome: %s", cmd_str)

    subprocess.Popen(cmd)

    try:
        downloaded = wait_for_new_download(
            download_dir,
            before,
            timeout_seconds=args.timeout,
            poll_seconds=args.poll,
            exts=DOWNLOAD_EXTS,
        )
    except TimeoutError as exc:
        logger.error("FAILED: %s", exc)
        return 1

    logger.info("Detected    : %s", downloaded)
    logger.info("Size        : %d bytes", downloaded.stat().st_size)

    final_path = move_or_copy_file(
        downloaded,
        output=args.output,
        keep_original=args.keep_original,
    )

    if args.output:
        action = "Copied to" if args.keep_original else "Moved to"
        logger.info("%s   : %s", action, final_path)
    else:
        logger.info("Saved in Downloads as-is.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
