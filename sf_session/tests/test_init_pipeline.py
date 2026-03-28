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
        "_PIPELINES_DIR": pipelines_dir,
        "_TEMPLATES_DIR": templates_dir,
    }
    with patch.multiple(init_pipeline, **patches):
        yield tmp_path


def _write_env(workspace: Path, pipelines: str) -> None:
    (workspace / ".env").write_text(
        f"PIPELINES={pipelines}\nMACRO_ROOT_PATH={workspace / 'macro'}\n"
        f"OUTPUT_ROOT_PATH={workspace / 'output'}\n",
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
        assert (pipeline_dir / "★01_download.bat").exists()
        # devtest-only bat should NOT exist for normal pipelines
        assert not (pipeline_dir / "■00_cleanup_test_csv.bat").exists()


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
    assert not (existing_dir / "★01_download.bat").exists()


def test_ensure_no_pipelines(workspace: Path):
    _write_env(workspace, "")

    # should simply return without error
    init_pipeline.ensure_pipelines()

    # pipelines/ should be empty
    assert list((workspace / "pipelines").iterdir()) == []


def test_ensure_creates_devtest_with_extra_bat(workspace: Path):
    _write_env(workspace, "devtest")

    init_pipeline.ensure_pipelines()

    pipeline_dir = workspace / "pipelines" / "devtest"
    assert pipeline_dir.is_dir()
    # common bat files should exist
    assert (pipeline_dir / "★01_download.bat").exists()
    # devtest-only bat should exist
    assert (pipeline_dir / "■00_cleanup_test_csv.bat").exists()
