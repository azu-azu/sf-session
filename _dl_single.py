"""内部モジュール: ログイン済み Chrome で SF レポートを1件 export し、ダウンロードを検知する。

dl_batch.py から利用される。直接実行は想定していない。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from config import SF_BASE_URL

logger = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────
DOWNLOAD_EXTS = {".csv", ".xls", ".xlsx"}


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


