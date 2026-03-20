"""sf-session 共通パス定数・ユーティリティ。"""
from __future__ import annotations

from pathlib import Path

from .utils import read_ids_file  # noqa: F401 — re-export

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# マクロ関連
MACRO_DIR = PROJECT_ROOT / "マクロ格納フォルダ"

# 出力フォルダ
CSV_STAGING_DIR = PROJECT_ROOT / "outputs_csv"
OUTPUT_RESULTS_DIR = PROJECT_ROOT / "outputs_result"

# Chrome
CHROME_EXE_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DATA_DIR = r"C:\ChromeProfile"

# Salesforce
SF_BASE_URL = "https://example.my.salesforce.com"

# ID フィルタ
DEFAULT_IDS_FILE = Path("レポートID/ids.txt")


def create_sf_client():
    """環境変数から Salesforce client を生成。.env があれば自動読み込み。"""
    import os

    from dotenv import load_dotenv
    from simple_salesforce import Salesforce

    load_dotenv()
    return Salesforce(
        username=os.environ["SF_USERNAME"],
        password=os.environ["SF_PASSWORD"],
        security_token=os.environ["SF_SECURITY_TOKEN"],
        domain=os.environ.get("SF_DOMAIN", "login"),
    )
