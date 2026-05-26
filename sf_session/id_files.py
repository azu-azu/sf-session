"""ID テキストファイルの読み取り。"""

from __future__ import annotations

from pathlib import Path


def find_latest_success_ids(results_dir: Path) -> Path | None:
    """results_dir から最新の success_ids_*.txt を返す。"""
    if not results_dir.is_dir():
        return None
    candidates = sorted(results_dir.glob("success_ids_*.txt"))
    return candidates[-1] if candidates else None


def read_ids_file(path: Path) -> set[str]:
    """ID テキストファイルを読み取り、set で返す。# 行はスキップ。"""
    if not path.exists():
        raise FileNotFoundError(f"ids-file not found: {path}")
    return {
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }
