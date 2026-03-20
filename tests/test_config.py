"""config.py のテスト。"""
from __future__ import annotations

import sys
from pathlib import Path

# sf-session root を sys.path に追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CSV_STAGING_DIR, DEFAULT_IDS_FILE, MACRO_DIR, PROJECT_ROOT


def test_project_root_is_sf_session():
    assert PROJECT_ROOT == Path(__file__).resolve().parent.parent


def test_macro_dir():
    assert MACRO_DIR == PROJECT_ROOT / "マクロ格納フォルダ"


def test_csv_staging_dir():
    assert CSV_STAGING_DIR == Path(r"Z:\Box\work\outputs_csv")


def test_default_ids_file():
    assert DEFAULT_IDS_FILE == Path("レポートID/ids.txt")
