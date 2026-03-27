"""sf-session 共通パス定数・ユーティリティ。"""
from __future__ import annotations

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

# Macro root
_MACRO_ROOT: Path | None = (
    Path(os.environ["MACRO_ROOT"]) if "MACRO_ROOT" in os.environ else None
)


# ── PipelineConfig ────────────────────────────────────
@dataclass(frozen=True)
class PipelineConfig:
    """pipeline ごとの設定。macro_dir は MACRO_ROOT/name で derive、他は convention ベース。"""

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
    """環境変数 PIPELINES (カンマ区切り) から pipeline 定義を読み込む。

    macro_dir は MACRO_ROOT / name で自動 derive する。
    """
    raw = os.environ.get("PIPELINES", "")
    if not raw:
        return {}
    if _MACRO_ROOT is None:
        raise ValueError("PIPELINES が設定されていますが MACRO_ROOT が未設定です")
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return {
        name: PipelineConfig(name=name, macro_dir=_MACRO_ROOT / name)
        for name in names
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
