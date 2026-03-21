"""マクロ格納フォルダの xlsm からジョブ定義を読み取る。

Usage:
    python -m sf_session.macro_book_reader
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from .config import DEFAULT_IDS_FILE, MACRO_DIR, OUTPUT_RESULTS_DIR, read_ids_file
from .utils import find_latest_success_ids

logger = logging.getLogger(__name__)

# --- 列定数（ローマ字） ---
_COL_NO = "AA"
_COL_URL = "AB"
_COL_NEW_FILENAME = "AC"
_COL_SRC_FOLDER_NAME = "AD"
_COL_ENCODE = "AE"
_COL_SKIP = "AG"

_SHEET_NAME = "SalseForce"

# データ開始行（100 = ヘッダ、101〜 = データ）
_DATA_START_ROW = 101


@dataclass
class JobEntry:
    """1行分のジョブ定義。"""

    no: str
    report_id: str | None
    has_filename: bool
    new_filename: str
    src_folder_name: str
    encode: str
    skip: str


def _col_to_index(col_letter: str) -> int:
    """Excel 列文字を 1-based インデックスに変換する。"""
    result = 0
    for ch in col_letter.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result


def _cell(ws, row: int, col_letter: str):
    """ワークシートからセル値を取得する。"""
    return ws.cell(row=row, column=_col_to_index(col_letter)).value


def _extract_id(url: str | None) -> str | None:
    """URL から末尾の ID を抽出する。"""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if "/" in url:
        return url.rsplit("/", 1)[-1]
    return url


def _has_filename(value) -> bool:
    """new_filename の指定があるか判定する。"""
    if value is None:
        return False
    s = str(value).strip()
    return bool(s) and s.isprintable()


def _find_xlsm(directory: Path) -> Path | None:
    """ディレクトリ内の .xlsm ファイルを1つ返す。"""
    files = list(directory.glob("*.xlsm"))
    if not files:
        return None
    if len(files) > 1:
        names = [f.name for f in files]
        logger.warning(".xlsm が複数あります: %s。最初のものを使用。", names)
    return files[0]


_RE_TRAILING_DATE = re.compile(r"_(\d{8})$")


def _strip_trailing_date(name: str) -> str:
    """末尾の _YYYYMMDD を除去する。日付として invalid or 今年でなければ何もしない。"""
    m = _RE_TRAILING_DATE.search(name)
    if not m:
        return name
    try:
        dt = datetime.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        return name
    if dt.year != datetime.now().year:
        return name
    return name[: m.start()]


def read_jobs_from_xlsm(xlsm_path: Path) -> list[JobEntry]:
    """指定した xlsm パスからジョブ定義を読み取る。"""
    wb = load_workbook(xlsm_path, read_only=True, data_only=True)
    ws = wb[_SHEET_NAME]

    entries: list[JobEntry] = []
    for row in range(_DATA_START_ROW, ws.max_row + 1):
        no = _cell(ws, row, _COL_NO)
        url = _cell(ws, row, _COL_URL)

        # No も URL も空なら終端
        if no is None and url is None:
            break

        raw_filename = _cell(ws, row, _COL_NEW_FILENAME)
        has_fn = _has_filename(raw_filename)

        entries.append(JobEntry(
            no=str(no) if no is not None else "",
            report_id=_extract_id(url),
            has_filename=has_fn,
            new_filename=_strip_trailing_date(str(raw_filename).strip()) if has_fn else "",
            src_folder_name=str(_cell(ws, row, _COL_SRC_FOLDER_NAME) or ""),
            encode=str(_cell(ws, row, _COL_ENCODE) or ""),
            skip=str(_cell(ws, row, _COL_SKIP) or ""),
        ))

    wb.close()
    return entries


def read_jobs(macro_dir: Path = MACRO_DIR) -> list[JobEntry]:
    """マクロ格納フォルダの xlsm からジョブ定義を読み取る。"""
    if not macro_dir.is_dir():
        raise FileNotFoundError(f"'{macro_dir}' が見つかりません。")

    xlsm_path = _find_xlsm(macro_dir)
    if xlsm_path is None:
        raise FileNotFoundError(
            f"'{macro_dir.name}/' に .xlsm がありません。"
        )

    logger.info("xlsm から読み取り: %s", xlsm_path.name)
    return read_jobs_from_xlsm(xlsm_path)


def load_active_jobs(
    macro_dir: Path = MACRO_DIR,
    *,
    ids_file: bool = False,
    exclude_success: bool = False,
) -> list[JobEntry]:
    """ジョブ定義を読み込み、skip / ids-file / success 除外でフィルタして返す。"""
    jobs = read_jobs(macro_dir)
    logger.info("ジョブ定義: %d 件読み取り", len(jobs))

    active = [j for j in jobs if not j.skip]
    logger.info(
        "実行対象: %d 件 (skip 除外: %d 件)",
        len(active), len(jobs) - len(active),
    )

    if ids_file:
        target_ids = read_ids_file(DEFAULT_IDS_FILE)
        before = len(active)
        active = [j for j in active if j.report_id in target_ids]
        logger.info(
            "ids-file フィルタ: %d 件 → %d 件 (ids-file: %d IDs)",
            before, len(active), len(target_ids),
        )

    if exclude_success:
        ids_path = find_latest_success_ids(OUTPUT_RESULTS_DIR)
        if ids_path is None:
            logger.warning("success_ids ファイルが見つかりません。除外なしで続行。")
        else:
            success_ids = read_ids_file(ids_path)
            before = len(active)
            active = [j for j in active if j.report_id not in success_ids]
            logger.info(
                "success 除外: %d 件 → %d 件 (%s: %d IDs)",
                before, len(active), ids_path.name, len(success_ids),
            )

    return active


def _log_jobs(entries: list[JobEntry]) -> None:
    """ジョブ定義をテーブル形式でターミナルに表示する。"""
    header = (
        f"{'No':<6} {'ID':<20} {'filename?':<10} "
        f"{'new_filename':<30} {'src_folder_name':<30} "
        f"{'encode':<10} {'skip':<6}"
    )
    lines = [header, "-" * len(header)]

    for e in entries:
        id_str = e.report_id or "(なし)"
        fn_flag = "True" if e.has_filename else "False"
        lines.append(
            f"{e.no:<6} {id_str:<20} {fn_flag:<10} "
            f"{e.new_filename:<30} {e.src_folder_name:<30} "
            f"{e.encode:<10} {e.skip:<6}"
        )

    lines.append(f"合計: {len(entries)} 件")
    logger.info("\n%s", "\n".join(lines))


if __name__ == "__main__":
    from .utils import setup_logging

    setup_logging()
    xlsm_path = _find_xlsm(MACRO_DIR)
    if xlsm_path is None:
        logger.error("'%s/' に .xlsm がありません。", MACRO_DIR.name)
    else:
        mtime = datetime.fromtimestamp(xlsm_path.stat().st_mtime)
        logger.info("ファイル: %s (更新: %s)", xlsm_path.name, mtime.strftime("%Y-%m-%d %H:%M"))
        jobs = read_jobs_from_xlsm(xlsm_path)
        _log_jobs(jobs)
