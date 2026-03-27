"""config.py のテスト。"""
from __future__ import annotations

from pathlib import Path

from sf_session.config import ARCHIVE_CSV_DIR, DEPLOY_ROOT, ARCHIVE_IDS_FILE, ARCHIVE_MACRO_DIR, PROJECT_ROOT


def test_project_root_is_sf_session():
    assert PROJECT_ROOT == Path(__file__).resolve().parent.parent.parent


def test_macro_dir():
    assert ARCHIVE_MACRO_DIR == PROJECT_ROOT / "マクロ格納フォルダ"


def test_deploy_root():
    """DEPLOY_ROOT が .env の値から Path として読み込まれていること。"""
    assert isinstance(DEPLOY_ROOT, Path)


def test_archive_csv_dir():
    """ARCHIVE_CSV_DIR が DEPLOY_ROOT / pipelines/archive/csv であること。"""
    assert ARCHIVE_CSV_DIR == DEPLOY_ROOT / "pipelines" / "archive" / "csv"


def test_archive_ids_file():
    assert ARCHIVE_IDS_FILE == DEPLOY_ROOT / "pipelines" / "archive" / "id_filter" / "ids.txt"
