import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def remove_dir(dir_path: Path, dry_run: bool = False) -> None:
    """ディレクトリを削除する。dry_run=Trueなら削除せず表示だけ行う。"""
    if dry_run:
        logger.info("[DRY-RUN] Remove dir : %s", dir_path)
        return

    try:
        shutil.rmtree(dir_path)
        logger.info("Removed dir : %s", dir_path)
    except OSError as e:
        logger.error("Remove dir %s: %s", dir_path, e)


def remove_file(file_path: Path, dry_run: bool = False) -> None:
    """ファイルを削除する。dry_run=Trueなら削除せず表示だけ行う。"""
    if dry_run:
        logger.info("[DRY-RUN] Remove file: %s", file_path)
        return

    try:
        file_path.unlink()
        logger.info("Removed file: %s", file_path)
    except OSError as e:
        logger.error("Remove file %s: %s", file_path, e)


def clean_directory(
    path: Path,
    clean_pycache: bool = True,
    clean_ide_configs: bool = True,
    clean_logs: bool = True,
    dry_run: bool = False,
) -> None:
    """
    指定ディレクトリ配下を再帰的に走査し、不要ファイル・不要ディレクトリを削除する。

    安全方針:
    - 仮想環境 (.venv / venv / env) は削除しない
    - .env は削除しない
    - ルート直下前提でも、再帰走査中に仮想環境っぽいディレクトリは潜らない
    """
    logger.info("--- Cleaning directory: %s ---", path)
    logger.info("dry_run = %s", dry_run)

    # 削除しない対象
    skip_dir_names = {".venv", "venv", "env"}
    skip_file_names = {".env"}

    # 常に削除するファイル名（カテゴリ不問）
    always_remove_files = {".DS_Store"}

    # 削除対象
    target_dir_names = set()
    if clean_pycache:
        target_dir_names.update({
            "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        })
    if clean_ide_configs:
        target_dir_names.update({".vscode", ".idea"})

    target_file_suffixes = set()
    if clean_pycache:
        target_file_suffixes.add(".pyc")
    if clean_logs:
        target_file_suffixes.update({".log", ".bak"})

    for root, dirs, files in os.walk(path, topdown=True):
        root_path = Path(root)

        # まず、仮想環境には入らないようにする
        dirs[:] = [d for d in dirs if d not in skip_dir_names]

        # 削除対象ディレクトリをここで処理し、探索対象からも外す
        dirs_to_remove = [d for d in dirs if d in target_dir_names]
        for d in dirs_to_remove:
            dir_path = root_path / d
            remove_dir(dir_path, dry_run=dry_run)

        dirs[:] = [d for d in dirs if d not in target_dir_names]

        # ファイル削除
        for file_name in files:
            if file_name in skip_file_names:
                continue

            file_path = root_path / file_name

            if file_name in always_remove_files:
                remove_file(file_path, dry_run=dry_run)
            elif file_path.suffix in target_file_suffixes:
                remove_file(file_path, dry_run=dry_run)

    logger.info("--- Clean-up complete. ---")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description=(
            "Pythonプロジェクトの不要ファイルを安全寄りにクリーンアップします。"
            "仮想環境 (.venv / venv / env) と .env は削除しません。"
        )
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="クリーンアップ対象ディレクトリ。省略時はカレントディレクトリ。",
    )
    parser.add_argument(
        "--no-pycache",
        action="store_true",
        help="__pycache__ ディレクトリと .pyc ファイルを削除しません。",
    )
    parser.add_argument(
        "--no-ide",
        action="store_true",
        help=".vscode / .idea ディレクトリを削除しません。",
    )
    parser.add_argument(
        "--no-logs",
        action="store_true",
        help=".log / .bak ファイルを削除しません。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際には削除せず、削除対象だけ表示します。",
    )

    args = parser.parse_args()
    target_dir = Path(args.target).resolve()

    if not target_dir.exists():
        logger.error("target does not exist: %s", target_dir)
        return 1

    if not target_dir.is_dir():
        logger.error("target is not a directory: %s", target_dir)
        return 1

    clean_directory(
        path=target_dir,
        clean_pycache=not args.no_pycache,
        clean_ide_configs=not args.no_ide,
        clean_logs=not args.no_logs,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
