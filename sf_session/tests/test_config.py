"""config.py のテスト。"""
from __future__ import annotations

from pathlib import Path

from sf_session.config import (
    PIPELINES,
    PipelineConfig,
    PROJECT_ROOT,
    VALID_PIPELINES,
)


def test_project_root_is_sf_session():
    assert PROJECT_ROOT == Path(__file__).resolve().parent.parent.parent


def test_archive_pipeline_exists():
    archive = PIPELINES["archive"]
    assert archive.macro_dir == Path(".")
    assert archive.csv_dir == PROJECT_ROOT / "pipelines" / "archive" / "csv"
    assert archive.ids_file == PROJECT_ROOT / "pipelines" / "archive" / "id_filter" / "ids.txt"


def test_valid_pipelines():
    assert isinstance(VALID_PIPELINES, tuple)
    assert "archive" in VALID_PIPELINES


def test_pipelines_dict():
    assert isinstance(PIPELINES, dict)
    assert "archive" in PIPELINES
    assert isinstance(PIPELINES["archive"], PipelineConfig)


def test_pipeline_config_derived_paths():
    cfg = PipelineConfig(name="test", macro_dir=Path("/tmp/macro"))
    assert cfg.csv_dir.name == "csv"
    assert "test" in str(cfg.csv_dir)
    assert cfg.result_dir.name == "result"
    assert cfg.ids_file.name == "ids.txt"
    assert "id_filter" in str(cfg.ids_file)
