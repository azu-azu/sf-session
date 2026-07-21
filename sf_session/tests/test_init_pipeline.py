"""init_pipeline.ensure_pipelines() のテスト。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from sf_session import init_pipeline


@pytest.fixture()
def workspace(tmp_path: Path):
    """tmp_path に .env と pipelines/ を用意し、module globals を差し替える。"""
    env_path = tmp_path / ".env"
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    templates_dir = tmp_path / "templates" / "pipeline"
    templates_dir.mkdir(parents=True)
    (templates_dir / "readme.txt").write_text("readme content", encoding="utf-8")

    patches = {
        "_ENV_PATH": env_path,
        "PIPELINES_DIR": pipelines_dir,
        "_TEMPLATES_DIR": templates_dir,
        "EXTRA_HOLIDAYS_PATH": pipelines_dir / "extra_holidays.csv",
        "MACRO_ROOT": tmp_path / "macro",
        "OUTPUT_ROOT": tmp_path / "output",
    }
    with patch.multiple(init_pipeline, **patches):
        yield tmp_path


def _write_env(workspace: Path, pipelines: str) -> None:
    (workspace / ".env").write_text(
        f"PIPELINES={pipelines}\n",
        encoding="utf-8",
    )


def test_ensure_creates_missing_pipeline(workspace: Path):
    _write_env(workspace, "alpha, bravo")

    init_pipeline.ensure_pipelines()

    for name in ("alpha", "bravo"):
        pipeline_dir = workspace / "pipelines" / name
        assert pipeline_dir.is_dir()
        assert (pipeline_dir / "result").is_dir()
        assert (pipeline_dir / "ids_file").is_dir()
        assert (pipeline_dir / "ids_file" / "ids.txt").exists()
        assert (pipeline_dir / "readme.txt").exists()
        # bat files
        assert (pipeline_dir / "01_download.bat").exists()
        # devtest-only bat should NOT exist for normal pipelines
        assert not (pipeline_dir / "00_cleanup_test_csv.bat").exists()
        # output / macro dirs
        assert (workspace / "output" / name / "csv").is_dir()
        assert (workspace / "macro" / name).is_dir()


def test_ensure_skips_existing_pipeline(workspace: Path):
    _write_env(workspace, "existing")
    existing_dir = workspace / "pipelines" / "existing"
    existing_dir.mkdir()
    marker = existing_dir / "marker.txt"
    marker.write_text("do not touch", encoding="utf-8")

    init_pipeline.ensure_pipelines()

    # marker file should remain untouched — no recreation happened
    assert marker.read_text(encoding="utf-8") == "do not touch"
    # no bat files should have been created
    assert not (existing_dir / "01_download.bat").exists()
    # output / macro dirs should still be created for existing pipelines
    assert (workspace / "output" / "existing" / "csv").is_dir()
    assert (workspace / "macro" / "existing").is_dir()


def test_ensure_no_pipelines(workspace: Path):
    _write_env(workspace, "")

    # should simply return without error
    init_pipeline.ensure_pipelines()

    # pipelines/ には extra_holidays.csv のみ
    children = [p.name for p in (workspace / "pipelines").iterdir()]
    assert children == ["extra_holidays.csv"]


def test_ensure_creates_extra_holidays_csv(workspace: Path):
    _write_env(workspace, "alpha")

    init_pipeline.ensure_pipelines()

    csv_path = workspace / "pipelines" / "extra_holidays.csv"
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    # テンプレートはコメント行のみ（実データなし）
    for line in content.splitlines():
        assert line == "" or line.lstrip().startswith("#")


def test_ensure_keeps_existing_extra_holidays_csv(workspace: Path):
    _write_env(workspace, "alpha")
    csv_path = workspace / "pipelines" / "extra_holidays.csv"
    csv_path.write_text("2026-12-31\n", encoding="utf-8")

    init_pipeline.ensure_pipelines()

    # 既存ファイルは上書きしない
    assert csv_path.read_text(encoding="utf-8") == "2026-12-31\n"


def test_regen_bats_overwrites_stale_bats(workspace: Path):
    _write_env(workspace, "alpha")
    pipeline_dir = workspace / "pipelines" / "alpha"
    pipeline_dir.mkdir()
    # 旧テンプレート相当（裸の pause）の bat を置いておく
    stale = pipeline_dir / "01_download.bat"
    stale.write_text(
        ".venv\\Scripts\\python.exe -m sf_session.download alpha %*\npause\n",
        encoding="utf-8",
    )

    init_pipeline.regenerate_bats()

    content = stale.read_text(encoding="utf-8")
    from sf_session.business_day import SKIP_EXIT_CODE

    # exit code を保存し、非営業日 skip のときだけ pause を飛ばす分岐が入っている
    assert 'set "rc=%errorlevel%"' in content
    assert f"if %rc% equ {SKIP_EXIT_CODE} exit /b 0" in content
    assert "if not defined SF_NO_PAUSE pause" in content
    # 保存した exit code を明示的に返している
    assert "exit /b %rc%" in content
    # 裸の pause 行は残っていない
    assert "\npause\n" not in content
    # 他の pipeline step bat も生成されている
    assert (pipeline_dir / "03_download_direct.bat").exists()


def test_regen_bats_skips_missing_pipeline_dir(workspace: Path):
    _write_env(workspace, "alpha")
    # pipelines/alpha を作らないまま regen → dir は作られず skip される

    init_pipeline.regenerate_bats()

    assert not (workspace / "pipelines" / "alpha").exists()


def test_regen_bats_no_pipelines(workspace: Path):
    _write_env(workspace, "")

    # 例外なく return するだけ
    init_pipeline.regenerate_bats()


def test_ensure_creates_devtest_with_extra_bat(workspace: Path):
    _write_env(workspace, "devtest")

    init_pipeline.ensure_pipelines()

    pipeline_dir = workspace / "pipelines" / "devtest"
    assert pipeline_dir.is_dir()
    # common bat files should exist
    assert (pipeline_dir / "01_download.bat").exists()
    # devtest-only bat should exist
    assert (pipeline_dir / "00_cleanup_test_csv.bat").exists()
