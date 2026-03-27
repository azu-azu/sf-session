"""sf-session 共通パス定数・ユーティリティ。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# マクロ関連
MACRO_DIR = Path(os.environ["MACRO_STORE_DIR"])

# 出力フォルダ
OUTPUT_STAGING_ROOT = Path(os.environ["OUTPUT_STAGING_ROOT"])
_OUTPUTS_DIR = OUTPUT_STAGING_ROOT / "outputs"
_ARCHIVE_DIR = _OUTPUTS_DIR / "archive"

_CSV_SUBDIR = "csv"
_RESULT_SUBDIR = "result"

ARCHIVE_CSV_DIR = _ARCHIVE_DIR / _CSV_SUBDIR
ARCHIVE_RESULT_DIR = _ARCHIVE_DIR / _RESULT_SUBDIR

# Chrome
CHROME_EXE_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DATA_DIR = r"C:\ChromeProfile"

# Salesforce
SF_BASE_URL = os.environ["SF_BASE_URL"]
SF_HOME_URL = f"{SF_BASE_URL}/home/home.jsp"

# ID フィルタ
DEFAULT_IDS_FILE = Path("レポートID/ids.txt")


def create_sf_client():
    """環境変数から Salesforce client を生成。"""
    from simple_salesforce import Salesforce

    return Salesforce(
        username=os.environ["SF_USERNAME"],
        password=os.environ["SF_PASSWORD"],
        security_token=os.environ["SF_SECURITY_TOKEN"],
        domain=os.environ.get("SF_DOMAIN", "login"),
    )
