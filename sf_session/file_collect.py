"""macro_book_reader のジョブ定義と success ID で対象 CSV を特定し、日付フォルダへコピーする。

file_dispatch の逆操作: 各フォルダから CSV を収集して CSV_STAGING_DIR に集約する。

Usage:
    python sf-session/file_collect.py
"""

import logging
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .config import CSV_STAGING_DIR, OUTPUT_RESULTS_DIR
from .macro_book_reader import JobEntry, read_jobs
from .utils import setup_logging

logger = logging.getLogger(__name__)

_COLLECT_FOLDER_TEMPLATE = "vba_#_jis"


def _find_latest_success_ids() -> Path | None:
    """outputs_result/ から最新の success_ids_*.txt を返す。"""
    if not OUTPUT_RESULTS_DIR.is_dir():
        return None
    candidates = sorted(OUTPUT_RESULTS_DIR.glob("success_ids_*.txt"))
    return candidates[-1] if candidates else None


def _read_success_ids(path: Path) -> set[str]:
    """success_ids テキストから report_id の集合を返す。"""
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _strip_date_suffix(name: str) -> str:
    """末尾の _YYYYMMDD を除去してベースパターンにする。"""
    return re.sub(r"_\d{8}$", "", name)


def _dump_csv_list(csvs: list[Path]) -> None:
    """フォルダ内の CSV ファイルと mtime を出力する（検索失敗時の診断用）。"""
    lines = [
        f"  {p.name}  mtime={datetime.fromtimestamp(p.stat().st_mtime)}"
        for p in csvs[:10]
    ]
    if len(csvs) > 10:
        lines.append(f"  ... 他 {len(csvs) - 10} 件")
    logger.warning("フォルダ内の CSV:\n%s", "\n".join(lines))


def _find_csv_by_name(
    source_folder: Path, name_fragment: str, today_str: str
) -> Path | None:
    """指定されたベース名 + 今日の日付サフィックスの CSV を優先的に返す。

    Network drive では mtime が信用できないため、ファイル名の日付を優先する。
    """
    csvs = list(source_folder.glob("*.csv"))
    today_exact = f"{name_fragment}_{today_str}.csv"

    for p in csvs:
        if p.name == today_exact:
            return p

    # fallback: name_fragment を含む CSV のうち mtime 最新
    matches = [p for p in csvs if name_fragment in p.name]
    if not matches:
        if csvs:
            _dump_csv_list(csvs)
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _find_csv_by_date(source_folder: Path, today_str: str) -> Path | None:
    """今日の日付サフィックス or 今日更新された CSV を検索する。"""
    csvs = list(source_folder.glob("*.csv"))

    for p in csvs:
        if p.name.lower().endswith(f"{today_str}.csv"):
            return p

    latest = None
    latest_mtime = None
    today_date = datetime.now().date()
    for p in csvs:
        mod_time = datetime.fromtimestamp(p.stat().st_mtime)
        if mod_time.date() == today_date:
            if latest is None or mod_time > latest_mtime:
                latest = p
                latest_mtime = mod_time

    if latest is None and csvs:
        _dump_csv_list(csvs)
    return latest


def _collect_one_job(
    job: JobEntry,
    today_str: str,
    daily_output_folder: Path,
) -> bool:
    """1ジョブ分の CSV を検索・コピーする。成功なら True。"""
    source_folder = Path(job.src_folder_name)
    if not source_folder.is_dir():
        logger.warning("フォルダが見つかりません: %s (No: %s)。スキップ。", source_folder, job.no)
        return False

    if job.has_filename:
        base = _strip_date_suffix(job.new_filename)
        target = _find_csv_by_name(source_folder, base, today_str)
        if target is None:
            logger.warning("'%s' を含む CSV が %s に見つかりません (No: %s)。スキップ。", base, source_folder, job.no)
            return False
    else:
        base = None
        target = _find_csv_by_date(source_folder, today_str)
        if target is None:
            logger.warning("今日の CSV が %s に見つかりません (No: %s)。スキップ。", source_folder, job.no)
            return False

    dest_name = (
        f"{job.report_id}_{base}_{today_str}.csv"
        if job.has_filename
        else f"{job.report_id}_{today_str}.csv"
    )
    destination = daily_output_folder / dest_name

    try:
        shutil.copy2(target, destination)
        logger.info("成功: From~ %s", target)
        return True
    except OSError as e:
        logger.error("コピー失敗 %s → %s: %s", target, destination, e)
        return False


def main() -> int:
    setup_logging()

    # --- setup ---
    try:
        jobs = read_jobs()
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    ids_path = _find_latest_success_ids()
    if ids_path is None:
        logger.error("success_ids ファイルが見つかりません。")
        return 1

    success_ids = _read_success_ids(ids_path)
    logger.info("success IDs: %s (%d 件)", ids_path.name, len(success_ids))

    today_str = datetime.now().strftime("%Y%m%d")
    new_folder_name = _COLLECT_FOLDER_TEMPLATE.replace("#", today_str)
    daily_output_folder = CSV_STAGING_DIR / new_folder_name

    if daily_output_folder.is_dir():
        removed = [f for f in daily_output_folder.iterdir() if f.is_file()]
        for f in removed:
            f.unlink()
        if removed:
            logger.info("既存 %d 件を削除: %s", len(removed), daily_output_folder.name)

    daily_output_folder.mkdir(parents=True, exist_ok=True)

    # --- collect ---
    ok_count = 0
    failed_ids: list[str] = []

    for job in jobs:
        if job.report_id not in success_ids:
            continue
        if _collect_one_job(job, today_str, daily_output_folder):
            ok_count += 1
        else:
            failed_ids.append(job.report_id or job.no)

    # --- summary ---
    logger.info("*" * 50)
    logger.info("file_collect complete >>")
    logger.info("成功 %d 件 / 失敗 %d 件 / 合計 %d 件", ok_count, len(failed_ids), ok_count + len(failed_ids))
    if failed_ids:
        logger.info("-" * 50)
        for fid in failed_ids:
            logger.info("  %s", fid)
    logger.info("*" * 50)

    return 1 if failed_ids else 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# Tests (run with pytest)
# ---------------------------------------------------------------------------

class TestStripDateSuffix:
    def test_strip(self):
        assert _strip_date_suffix("01_RPT_20260313") == "01_RPT"

    def test_no_date(self):
        assert _strip_date_suffix("01_RPT") == "01_RPT"

    def test_date_in_middle_untouched(self):
        assert _strip_date_suffix("01_20260313_RPT") == "01_20260313_RPT"

    def test_empty(self):
        assert _strip_date_suffix("") == ""


class TestFindCsvByName:
    def test_today_exact_match(self, tmp_path):
        """今日の日付サフィックスが完全一致するファイルを優先する。"""
        target = tmp_path / "01_RPT_20260319.csv"
        target.write_text("data")
        (tmp_path / "01_RPT_20260318.csv").write_text("old")
        (tmp_path / "other.csv").write_text("x")

        result = _find_csv_by_name(tmp_path, "01_RPT", "20260319")
        assert result == target

    def test_today_preferred_over_newer_mtime(self, tmp_path):
        """mtime が古くても今日の日付ファイルが優先される。"""
        import os

        today = tmp_path / "01_RPT_20260319.csv"
        today.write_text("today")
        past = datetime(2026, 3, 19, 1, 0).timestamp()
        os.utime(today, (past, past))

        yesterday = tmp_path / "01_RPT_20260318.csv"
        yesterday.write_text("yesterday")
        # mtime は now → today より新しい

        result = _find_csv_by_name(tmp_path, "01_RPT", "20260319")
        assert result == today

    def test_fallback_to_mtime(self, tmp_path):
        """今日の日付ファイルがなければ mtime fallback。"""
        target = tmp_path / "report_daily_20260318.csv"
        target.write_text("data")

        result = _find_csv_by_name(tmp_path, "report_daily", "20260319")
        assert result == target

    def test_not_found(self, tmp_path):
        (tmp_path / "report.csv").write_text("data")
        assert _find_csv_by_name(tmp_path, "missing", "20260319") is None

    def test_empty_folder(self, tmp_path):
        assert _find_csv_by_name(tmp_path, "any", "20260319") is None

    def test_non_csv_ignored(self, tmp_path):
        (tmp_path / "report_daily.txt").write_text("data")
        assert _find_csv_by_name(tmp_path, "report_daily", "20260319") is None

    def test_japanese_filename_fallback(self, tmp_path):
        """日本語名ファイルも mtime fallback で拾える。"""
        import os, time

        old_jp = tmp_path / "01_RPT_全件.csv"
        old_jp.write_text("old")
        past = datetime(2025, 12, 23).timestamp()
        os.utime(old_jp, (past, past))

        time.sleep(0.05)
        newer = tmp_path / "01_RPT_20260318.csv"
        newer.write_text("new")

        result = _find_csv_by_name(tmp_path, "01_RPT", "20260319")
        assert result == newer  # 今日はないが mtime fallback

    def test_with_stripped_base_picks_today(self, tmp_path):
        """呼び出し側が _strip_date_suffix 済みの base を渡すケース。"""
        import os

        for i, (name, days_ago) in enumerate([
            ("01_RPT_20260313.csv", 6),
            ("01_RPT_20260316.csv", 3),
            ("01_RPT_20260319.csv", 0),
        ]):
            f = tmp_path / name
            f.write_text(f"data{i}")
            ts = datetime(2026, 3, 19 - days_ago, 9, 0).timestamp()
            os.utime(f, (ts, ts))

        base = _strip_date_suffix("01_RPT_20260313")
        result = _find_csv_by_name(tmp_path, base, "20260319")
        assert result == tmp_path / "01_RPT_20260319.csv"


class TestFindCsvByDate:
    def test_suffix_match(self, tmp_path):
        target = tmp_path / "report20260314.csv"
        target.write_text("data")

        result = _find_csv_by_date(tmp_path, "20260314")
        assert result == target

    def test_suffix_match_lowercase_ext(self, tmp_path):
        target = tmp_path / "REPORT20260314.csv"
        target.write_text("data")

        result = _find_csv_by_date(tmp_path, "20260314")
        assert result == target

    def test_mtime_fallback(self, tmp_path):
        target = tmp_path / "report.csv"
        target.write_text("data")

        today_str = datetime.now().strftime("%Y%m%d")
        result = _find_csv_by_date(tmp_path, today_str)
        assert result == target

    def test_no_match(self, tmp_path):
        import os

        (tmp_path / "old20200101.csv").write_text("data")
        past = datetime(2020, 1, 1).timestamp()
        os.utime(tmp_path / "old20200101.csv", (past, past))

        result = _find_csv_by_date(tmp_path, "20260314")
        assert result is None

    def test_picks_latest_mtime(self, tmp_path):
        import time

        today_str = datetime.now().strftime("%Y%m%d")

        (tmp_path / "a.csv").write_text("1")

        time.sleep(0.05)
        f2 = tmp_path / "b.csv"
        f2.write_text("2")

        result = _find_csv_by_date(tmp_path, today_str)
        assert result == f2
