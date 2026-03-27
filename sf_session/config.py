"""sf-session 共通パス定数・ユーティリティ。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── 共通 ──────────────────────────────────────────────
OUTPUT_STAGING_ROOT = Path(os.environ["OUTPUT_STAGING_ROOT"])
OUTPUTS_DIR = OUTPUT_STAGING_ROOT / "outputs"

_CSV_SUBDIR = "csv"
_RESULT_SUBDIR = "result"
_ID_FILTER_SUBDIR = "id_filter"

# Chrome
CHROME_EXE_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DATA_DIR = r"C:\ChromeProfile"

# Salesforce
SF_BASE_URL = os.environ["SF_BASE_URL"]
SF_HOME_URL = f"{SF_BASE_URL}/home/home.jsp"

# ── archive pipeline ─────────────────────────────────
_ARCHIVE_DIR = OUTPUTS_DIR / "archive"

ARCHIVE_MACRO_DIR = Path(os.environ["ARCHIVE_MACRO_DIR"])
ARCHIVE_CSV_DIR = _ARCHIVE_DIR / _CSV_SUBDIR
ARCHIVE_RESULT_DIR = _ARCHIVE_DIR / _RESULT_SUBDIR
ARCHIVE_IDS_FILE = _ARCHIVE_DIR / _ID_FILTER_SUBDIR / "ids.txt"


def create_sf_client():
    """環境変数から Salesforce client を生成。"""
    from simple_salesforce import Salesforce

    return Salesforce(
        username=os.environ["SF_USERNAME"],
        password=os.environ["SF_PASSWORD"],
        security_token=os.environ["SF_SECURITY_TOKEN"],
        domain=os.environ.get("SF_DOMAIN", "login"),
    )
