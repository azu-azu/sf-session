"""sf-session 共通パス定数・ユーティリティ。"""
from __future__ import annotations

from pathlib import Path

from .utils import read_ids_file  # noqa: F401 — re-export

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# マクロ関連
MACRO_DIR = PROJECT_ROOT / "マクロ格納フォルダ"

# 出力フォルダ
def _load_csv_staging_dir() -> Path:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    val = os.environ.get("CSV_STAGING_DIR")
    return Path(val) if val else PROJECT_ROOT / "outputs_csv"

CSV_STAGING_DIR = _load_csv_staging_dir()
OUTPUT_RESULTS_DIR = PROJECT_ROOT / "outputs_result"
OUTPUT_LOG_DIR = PROJECT_ROOT / "outputs_log"
OUTPUT_ERRORS_DIR = OUTPUT_LOG_DIR / "errors"

# report_filter 用
PIPELINE_DIR = PROJECT_ROOT / "pipelines"
FILTER_OUTPUT_DIR = OUTPUT_LOG_DIR / "report_filters"
DEFAULT_FILTER_OUTPUT = FILTER_OUTPUT_DIR / "report_filters.json"

# Chrome
CHROME_EXE_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DATA_DIR = r"C:\ChromeProfile"

# Salesforce
def _load_sf_base_url() -> str:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    return os.environ["SF_BASE_URL"]

SF_BASE_URL = _load_sf_base_url()
SF_HOME_URL = f"{SF_BASE_URL}/home/home.jsp"

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
