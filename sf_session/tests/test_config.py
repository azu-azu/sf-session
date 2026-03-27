"""config.py のテスト。"""
from __future__ import annotations

from pathlib import Path

from sf_session.config import ARCHIVE_CSV_DIR, OUTPUT_STAGING_ROOT, DEFAULT_IDS_FILE, MACRO_DIR, PROJECT_ROOT


def test_project_root_is_sf_session():
    assert PROJECT_ROOT == Path(__file__).resolve().parent.parent.parent


def test_macro_dir():
    assert MACRO_DIR == PROJECT_ROOT / "マクロ格納フォルダ"


def test_csv_staging_root():
    """OUTPUT_STAGING_ROOT が .env の値から Path として読み込まれていること。"""
    assert isinstance(OUTPUT_STAGING_ROOT, Path)


def test_csv_staging_dir():
    """ARCHIVE_CSV_DIR が OUTPUT_STAGING_ROOT / outputs/archive/csv であること。"""
    assert ARCHIVE_CSV_DIR == OUTPUT_STAGING_ROOT / "outputs" / "archive" / "csv"


def test_default_ids_file():
    assert DEFAULT_IDS_FILE == Path("レポートID/ids.txt")
