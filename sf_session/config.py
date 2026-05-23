"""sf-session 共通パス定数・ユーティリティ。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── 共通 ──────────────────────────────────────────────
PIPELINES_DIR = PROJECT_ROOT / "pipelines"

_CSV_SUBDIR = "csv"
_RESULT_SUBDIR = "result"
_IDS_FILE_SUBDIR = "ids_file"

USER_HOME = Path.home()
USER_NAME = USER_HOME.name


def _expand_path(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def _normalize_path(path: Path) -> str:
    return str(path).replace("/", "\\")


def _is_z_drive(normalized: str) -> bool:
    return normalized[:2].lower() == "z:"


def _needs_home_fallback(path: Path) -> bool:
    return _is_z_drive(_normalize_path(path)) and not path.exists()


def _to_home_fallback(normalized: str) -> Path:
    return Path.home() / normalized[3:]


# Path
_MACRO_ROOT_RAW = os.environ.get("MACRO_ROOT_PATH")
_OUTPUT_ROOT_RAW = os.environ.get("OUTPUT_ROOT_PATH")

if _MACRO_ROOT_RAW is None:
    USE_HOME_FALLBACK = False
else:
    USE_HOME_FALLBACK = _needs_home_fallback(_expand_path(_MACRO_ROOT_RAW))


def resolve_project_path(raw: str | Path) -> Path:
    """外部由来の path を resolve する。
    Z: が見つからなければ ~/ に fallback."""
    path = _expand_path(str(raw))
    normalized = _normalize_path(path)
    
    if USE_HOME_FALLBACK and _is_z_drive(normalized):
        return _to_home_fallback(normalized)
    return path


MACRO_ROOT: Path | None = (
    resolve_project_path(_MACRO_ROOT_RAW) if _MACRO_ROOT_RAW else None
)

OUTPUT_ROOT: Path | None = (
    resolve_project_path(_OUTPUT_ROOT_RAW) if _OUTPUT_ROOT_RAW else None
)


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
    """pipeline ごとの設定。macro_dir は MACRO_ROOT/name で組み立て 、他は ルール通り。"""

    name: str
    macro_dir: Path

    @property
    def csv_dir(self) -> Path:
        if OUTPUT_ROOT is not None:
            return OUTPUT_ROOT / self.name / _CSV_SUBDIR
        return PIPELINES_DIR / self.name / _CSV_SUBDIR

    @property
    def result_dir(self) -> Path:
        return PIPELINES_DIR / self.name / _RESULT_SUBDIR

    @property
    def ids_dir(self) -> Path:
        return PIPELINES_DIR / self.name / _IDS_FILE_SUBDIR

    @property
    def ids_file(self) -> Path:
        return self.ids_dir / "ids.txt"


def _load_pipelines() -> dict[str, PipelineConfig]:
    """環境変数 PIPELINES (カンマ区切り) から pipeline 定義を読み込む。

    macro_dir は MACRO_ROOT / name で自動 derive する。
    """
    raw = os.environ.get("PIPELINES", "")
    if not raw:
        return {}
    if MACRO_ROOT is None:
        raise ValueError("PIPELINES が設定されていますが MACRO_ROOT_PATH が未設定です")
    if OUTPUT_ROOT is None:
        raise ValueError("PIPELINES が設定されていますが OUTPUT_ROOT_PATH が未設定です")
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return {
        name: PipelineConfig(name=name, macro_dir=MACRO_ROOT / name)
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
