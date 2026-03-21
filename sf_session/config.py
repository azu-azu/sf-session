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
SF_BASE_URL = "https://example.my.salesforce.com"
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


def get_login_credentials() -> tuple[str, str]:
    """UI ログイン用の credentials を返す。専用変数がなければ API 用にフォールバック。"""
    import os

    from dotenv import load_dotenv

    load_dotenv()
    username = os.environ.get("SF_LOGIN_USERNAME") or os.environ["SF_USERNAME"]
    password = os.environ.get("SF_LOGIN_PASSWORD") or os.environ["SF_PASSWORD"]
    return username, password
