"""config.py のテスト。"""
from __future__ import annotations

from pathlib import Path

from sf_session.config import CSV_STAGING_DIR, CSV_STAGING_ROOT, DEFAULT_IDS_FILE, MACRO_DIR, PROJECT_ROOT


def test_project_root_is_sf_session():
    assert PROJECT_ROOT == Path(__file__).resolve().parent.parent.parent


def test_macro_dir():
    assert MACRO_DIR == PROJECT_ROOT / "マクロ格納フォルダ"


def test_csv_staging_root():
    """CSV_STAGING_ROOT が .env の値から Path として読み込まれていること。"""
    assert isinstance(CSV_STAGING_ROOT, Path)


def test_csv_staging_dir():
    """CSV_STAGING_DIR が CSV_STAGING_ROOT / outputs_csv であること。"""
    assert CSV_STAGING_DIR == CSV_STAGING_ROOT / "outputs_csv"


def test_default_ids_file():
    assert DEFAULT_IDS_FILE == Path("レポートID/ids.txt")
