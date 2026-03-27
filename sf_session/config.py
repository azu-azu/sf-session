"""sf-session 共通パス定数・ユーティリティ。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── 共通 ──────────────────────────────────────────────
_PIPELINES_DIR = PROJECT_ROOT / "pipelines"

_CSV_SUBDIR = "csv"
_RESULT_SUBDIR = "result"
_ID_FILTER_SUBDIR = "id_filter"

# Chrome
CHROME_EXE_PATH = os.environ.get(
    "CHROME_EXE_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)
CHROME_USER_DATA_DIR = os.environ.get("CHROME_USER_DATA_DIR", r"C:\ChromeProfile")

# Salesforce
SF_BASE_URL = os.environ["SF_BASE_URL"]
SF_HOME_URL = f"{SF_BASE_URL}/home/home.jsp"


# ── PipelineConfig ────────────────────────────────────
@dataclass(frozen=True)
class PipelineConfig:
    """pipeline ごとの設定。macro_dir のみ外部指定、他は convention ベースで derive。"""

    name: str
    macro_dir: Path

    @property
    def csv_dir(self) -> Path:
        return _PIPELINES_DIR / self.name / _CSV_SUBDIR

    @property
    def result_dir(self) -> Path:
        return _PIPELINES_DIR / self.name / _RESULT_SUBDIR

    @property
    def ids_file(self) -> Path:
        return _PIPELINES_DIR / self.name / _ID_FILTER_SUBDIR / "ids.txt"


def _load_pipelines() -> dict[str, PipelineConfig]:
    """環境変数 PIPELINES (JSON) から pipeline 定義を読み込む。

    Format: {"archive": "マクロ格納フォルダ", "daily": "日次マクロフォルダ"}
    """
    raw = os.environ.get("PIPELINES", "")
    if not raw:
        return {}
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"PIPELINES の JSON が不正です: {e}") from e
    if not isinstance(mapping, dict):
        raise ValueError("PIPELINES は JSON object で指定してください")
    return {
        name: PipelineConfig(name=name, macro_dir=Path(path))
        for name, path in mapping.items()
    }


PIPELINES: dict[str, PipelineConfig] = _load_pipelines()
VALID_PIPELINES = tuple(PIPELINES)


def create_sf_client():
    """環境変数から Salesforce client を生成。"""
    from simple_salesforce import Salesforce

    return Salesforce(
        username=os.environ["SF_USERNAME"],
        password=os.environ["SF_PASSWORD"],
        security_token=os.environ["SF_SECURITY_TOKEN"],
        domain=os.environ.get("SF_DOMAIN", "login"),
    )
