"""download の出力関連ユーティリティ。

ファイルの移動先パス組み立て、summary ログ、success_ids 書き出し、
work_dir 準備 / swap / marker 作成、output dir の物理チェック・Explorer 表示を担う。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runner import ExportResult

from ..macro_book_reader import JobEntry
from ..utils import build_output_stem, time_label

logger = logging.getLogger(__name__)


# ── ファイルパス組み立て ──────────────────────────────────


def build_destination(
    job: JobEntry,
    downloaded: Path,
    *,
    output_dir: Path | None = None,
) -> Path:
    """ダウンロードファイルの移動先パスを組み立てる。

    ファイル名は {report_id}_{YYYYMMDD}_{stem}{ext} 形式。
    rename 指定 (has_filename) があれば stem = new_filename、なければ元ファイル名。
    output_dir が指定されていれば全ファイルをそこに出力し、
    未指定なら job.src_folder_name を使う。
    """
    dest_dir = output_dir if output_dir else Path(job.src_folder_name)
    ext = downloaded.suffix
    raw_stem = job.new_filename if job.has_filename else downloaded.stem
    stem = build_output_stem(job.report_id, raw_stem)

    return dest_dir / f"{stem}{ext}"


# ── サマリー / 結果出力 ──────────────────────────────────


def log_summary(results: list[ExportResult]) -> tuple[int, int]:
    """実行結果のサマリーをログ出力し、(ok, ng) を返す。"""
    ok = sum(1 for r in results if r.success)
    ng = sum(1 for r in results if not r.success)

    logger.info("*" * 50)
    logger.info("download complete >>")
    logger.info("成功 %d 件 / 失敗 %d 件 / 合計 %d 件", ok, ng, len(results))

    failures = [r for r in results if not r.success]
    if failures:
        logger.info("-" * 50)
        for r in failures:
            dest = r.dest_path or "-"
            err = f" ({r.error})" if r.error else ""
            logger.info(
                "  [NG] %d件目 %s  %.1fs  %s%s",
                r.seq, r.report_id, r.elapsed, dest, err,
            )

    logger.info("*" * 50)

    return ok, ng


def write_success_ids(results: list[ExportResult], *, result_dir: Path) -> Path | None:
    """成功した report_id を result_dir/success_ids_YYYYMMDD.txt に書き出す。"""
    ids = [r.report_id for r in results if r.success and r.report_id]
    if not ids:
        return None

    result_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    path = result_dir / f"success_ids_{today}.txt"
    path.write_text("\n".join(ids) + "\n", encoding="utf-8")
    logger.info("success_ids を書き出し: %s (%d 件)", path.name, len(ids))
    return path


# ── output dir probe / open ──────────────────────────────


def probe_output_dir(path: Path, *, mkdir: bool = False) -> None:
    """output dir が物理的にアクセス可能か probe する。

    touch + unlink で書き込み可能性をチェック。
    ネットワークドライブが切れている等の場合に早期失敗させる。

    mkdir=True の場合、親ディレクトリが存在すれば最終フォルダだけ自動作成する。
    """
    if not path.is_dir():
        if mkdir and path.parent.is_dir():
            if path.exists():
                raise FileNotFoundError(
                    f"出力先パスがファイルとして存在します: {path}"
                )
            path.mkdir()
            logger.info("出力先ディレクトリを作成しました: %s", path)
        else:
            raise FileNotFoundError(f"出力先ディレクトリが存在しません: {path}")

    probe_file = path / ".sf_session_probe"
    try:
        probe_file.touch()
        probe_file.unlink()
    except OSError as e:
        raise OSError(f"出力先ディレクトリに書き込めません: {path} ({e})") from e


def probe_destinations(jobs: list[JobEntry], *, mkdir: bool = False) -> list[str]:
    """job 定義の全移動先フォルダを probe し、エラーメッセージのリストを返す。

    空リストなら全フォルダ OK。
    mkdir=True なら親が存在する場合に最終フォルダを自動作成する。
    """
    seen: set[str] = set()
    errors: list[str] = []
    for job in jobs:
        folder = job.src_folder_name
        if not folder or folder in seen:
            continue
        seen.add(folder)
        try:
            probe_output_dir(Path(folder), mkdir=mkdir)
        except (FileNotFoundError, OSError) as e:
            errors.append(str(e))
    return errors


def open_folder(path: Path) -> None:
    """フォルダを OS のファイルマネージャで開く。

    network path (UNC / mapped drive) では Path.is_dir() や resolve() が
    不安定なため、チェックせず OS に直接委譲する。
    """
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        logger.info("フォルダを開きました: %s", path)
    except OSError as e:
        logger.warning("open_folder 失敗: %s (%s)", path, e)


# ── work_dir 管理 ────────────────────────────────────────

_TS_FMT = "%Y%m%d_%H%M%S"


def prepare_work_dir(staging_dir: Path) -> Path:
    """timestamp 付きの work_dir を作成して返す。"""
    _cleanup_old_dirs(staging_dir, "_work_")
    ts = datetime.now().strftime(_TS_FMT)
    work_dir = staging_dir.with_name(f"{staging_dir.name}_work_{ts}")
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def write_start_marker(output_dir: Path, total: int) -> Path:
    """開始マーカーファイルを作成して返す。"""
    marker = output_dir / f"★{time_label()}_START_{total}件の予定.txt"
    marker.touch()
    logger.info("開始マーカー: %s", marker.name)
    return marker


def write_marker(output_dir: Path, ok: int, ng: int) -> Path:
    """完了マーカーファイルを作成して返す。"""
    marker = output_dir / f"★{time_label()}_成功{ok}件_失敗{ng}件.txt"
    marker.touch()
    logger.info("完了マーカー: %s", marker.name)
    return marker


def swap_work_to_staging(
    work_dir: Path, staging_dir: Path, ok_count: int,
) -> None:
    """work_dir → staging_dir に atomic swap。

    ok_count=0 なら swap しない（前回の正常な current を保持）。
    前回分は _prev_{ts} に退避し、旧世代の _prev_* は事前に削除する（2世代制限）。
    """
    if ok_count == 0:
        logger.warning("success 0 件のため swap しない")
        return

    _cleanup_old_dirs(staging_dir, "_prev_")

    if staging_dir.is_dir():
        ts = datetime.now().strftime(_TS_FMT)
        prev_dir = staging_dir.with_name(f"{staging_dir.name}_prev_{ts}")
        staging_dir.rename(prev_dir)

    work_dir.rename(staging_dir)
    logger.info("swap 完了: %s → %s", work_dir.name, staging_dir.name)


def _cleanup_old_dirs(staging_dir: Path, infix: str) -> None:
    """staging_dir と同階層の {staging_dir.name}{infix}* を全削除する。"""
    parent = staging_dir.parent
    pattern = f"{staging_dir.name}{infix}*"
    for d in sorted(parent.glob(pattern)):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            logger.info("旧世代削除: %s", d.name)
