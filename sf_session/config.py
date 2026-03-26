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
_CSV_STAGING_SUBDIR = "outputs_csv"

CSV_STAGING_ROOT = Path(os.environ["CSV_STAGING_ROOT"])
CSV_STAGING_DIR = CSV_STAGING_ROOT / _CSV_STAGING_SUBDIR
OUTPUT_RESULTS_DIR = PROJECT_ROOT / "outputs_result"
OUTPUT_LOG_DIR = PROJECT_ROOT / "outputs_log"
OUTPUT_ERRORS_DIR = OUTPUT_LOG_DIR / "errors"

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
