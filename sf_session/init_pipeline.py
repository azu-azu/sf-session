"""New pipeline scaffolding tool.

Usage:
    python -m sf_session.init_pipeline
"""

from __future__ import annotations

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
_PIPELINES_DIR = _PROJECT_ROOT / "pipelines"
_TEMPLATE_PIPELINE = "archive"
_SUBDIRS = ("csv", "result", "id_filter")


# ── helpers ──────────────────────────────────────────────────────────


def _read_env_value(key: str) -> str | None:
    """Read a single value from .env without importing config."""
    if not _ENV_PATH.exists():
        return None
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith(f"{key}="):
            return stripped.split("=", 1)[1].strip()
    return None


def _existing_pipelines() -> list[str]:
    raw = _read_env_value("PIPELINES") or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def _update_env_pipelines(new_name: str) -> str:
    """Append *new_name* to the PIPELINES line in .env and return the updated value."""
    text = _ENV_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r"^(PIPELINES\s*=\s*)(.+?)(\s*(?:#.*)?)$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise RuntimeError("PIPELINES line not found in .env")

    current = match.group(2).strip()
    updated = f"{current}, {new_name}"
    new_text = pattern.sub(rf"\g<1>{updated}\3", text)
    _ENV_PATH.write_text(new_text, encoding="utf-8")
    return updated


def _create_directories(name: str) -> Path:
    pipeline_dir = _PIPELINES_DIR / name
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    for sub in _SUBDIRS:
        (pipeline_dir / sub).mkdir(exist_ok=True)
    return pipeline_dir


def _copy_bat_files(name: str, pipeline_dir: Path) -> int:
    template_dir = _PIPELINES_DIR / _TEMPLATE_PIPELINE
    count = 0
    for src in sorted(template_dir.glob("*.bat")):
        content = src.read_text(encoding="utf-8")
        content = content.replace(f" {_TEMPLATE_PIPELINE}", f" {name}")
        (pipeline_dir / src.name).write_text(content, encoding="utf-8")
        count += 1
    return count


def _ensure_macro_dir(name: str) -> tuple[Path, bool]:
    macro_root_raw = _read_env_value("MACRO_ROOT")
    if not macro_root_raw:
        raise RuntimeError("MACRO_ROOT not found in .env")
    macro_dir = Path(macro_root_raw) / name
    created = not macro_dir.exists()
    macro_dir.mkdir(parents=True, exist_ok=True)
    return macro_dir, created


# ── main ─────────────────────────────────────────────────────────────


def main() -> None:
    name = input("pipeline名を入力してください: ").strip()

    # validation
    if not name:
        print("[ERROR] pipeline名が空です")
        return
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        print("[ERROR] pipeline名は英数字・ハイフン・アンダースコアのみ使用できます")
        return
    existing = _existing_pipelines()
    if name in existing:
        print(f"[ERROR] pipeline '{name}' は既に存在します: {', '.join(existing)}")
        return

    # 1. update .env
    updated = _update_env_pipelines(name)
    print(f"\n✓ .env の PIPELINES を更新しました: {updated}")

    # 2. create directories
    pipeline_dir = _create_directories(name)
    print(f"✓ pipelines/{name}/ を作成しました")
    for sub in _SUBDIRS:
        print(f"  - {sub}/")

    # 3. copy bat files
    count = _copy_bat_files(name, pipeline_dir)
    print(f"✓ bat ファイルを配置しました ({count} files)")

    # 4. macro directory
    try:
        macro_dir, created = _ensure_macro_dir(name)
        if created:
            print(f"✓ {macro_dir} を作成しました")
            print(f"⚠ マクロファイル (.xlsm) を {macro_dir} に格納してください")
        else:
            print(f"✓ {macro_dir} は既に存在します")
    except RuntimeError as e:
        print(f"⚠ MACRO_ROOT の処理をスキップしました: {e}")

    print("\nセットアップ完了！")


if __name__ == "__main__":
    main()
