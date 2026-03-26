"""single.py の unit test。"""

from __future__ import annotations

from pathlib import Path

import pytest

from sf_session.config import SF_BASE_URL
from sf_session.download.single import (
    build_chrome_command,
    build_export_url,
    ensure_exists,
    is_temporary_download,
    resolve_download_dir,
    snapshot_files,
    wait_for_new_download,
)


# ── build_export_url ─────────────────────────────────────


class TestBuildExportUrl:
    def test_default_params(self):
        url = build_export_url("00O123")
        assert url == f"{SF_BASE_URL}/00O123?isdtp=p1&export=1&enc=UTF-8&xf=csv"

    def test_custom_enc_fmt(self):
        url = build_export_url("00O456", enc="Shift_JIS", fmt="xls")
        assert url == f"{SF_BASE_URL}/00O456?isdtp=p1&export=1&enc=Shift_JIS&xf=xls"


# ── snapshot_files ───────────────────────────────────────


class TestSnapshotFiles:
    def test_returns_matching_files(self, tmp_path):
        csv = tmp_path / "report.csv"
        csv.write_text("data")
        txt = tmp_path / "readme.txt"
        txt.write_text("hello")

        result = snapshot_files(tmp_path, {".csv"})

        assert "report.csv" in result
        assert "readme.txt" not in result
        assert isinstance(result["report.csv"], float)

    def test_ignores_directories(self, tmp_path):
        d = tmp_path / "foo.csv"
        d.mkdir()

        result = snapshot_files(tmp_path, {".csv"})

        assert result == {}

    def test_empty_directory(self, tmp_path):
        assert snapshot_files(tmp_path, {".csv"}) == {}


# ── is_temporary_download ────────────────────────────────


class TestIsTemporaryDownload:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("file.crdownload", True),
            ("FILE.TMP", True),
            ("data.part", True),
            ("report.csv", False),
        ],
    )
    def test_detection(self, name, expected):
        assert is_temporary_download(Path(name)) is expected


# ── wait_for_new_download ────────────────────────────────


class TestWaitForNewDownload:
    def test_detects_new_file(self, tmp_path, monkeypatch):
        csv = tmp_path / "report.csv"
        csv.write_text("data")

        # time.time が deadline を超えないよう2回だけ呼ばれる
        times = iter([0, 100])
        monkeypatch.setattr(
            "sf_session.download.single.time.time", lambda: next(times),
        )
        monkeypatch.setattr(
            "sf_session.download.single.time.sleep", lambda _: None,
        )

        result = wait_for_new_download(
            tmp_path, {}, timeout_seconds=200, poll_seconds=0, exts={".csv"},
        )
        assert result == csv

    def test_timeout_raises(self, tmp_path, monkeypatch):
        # deadline に即到達させる
        times = iter([100, 200])
        monkeypatch.setattr(
            "sf_session.download.single.time.time", lambda: next(times),
        )
        monkeypatch.setattr(
            "sf_session.download.single.time.sleep", lambda _: None,
        )

        with pytest.raises(TimeoutError):
            wait_for_new_download(
                tmp_path, {}, timeout_seconds=1, poll_seconds=0, exts={".csv"},
            )


# ── resolve_download_dir ─────────────────────────────────


class TestResolveDownloadDir:
    def test_with_arg(self, tmp_path):
        result = resolve_download_dir(str(tmp_path / "dl"))
        assert result == (tmp_path / "dl").resolve()

    def test_default_none(self):
        result = resolve_download_dir(None)
        assert result == (Path.home() / "Downloads").resolve()


# ── ensure_exists ────────────────────────────────────────


class TestEnsureExists:
    def test_existing_path_ok(self, tmp_path):
        ensure_exists(tmp_path, "test dir")  # should not raise

    def test_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Chrome"):
            ensure_exists(tmp_path / "nonexistent", "Chrome")


# ── build_chrome_command ─────────────────────────────────


class TestBuildChromeCommand:
    def test_minimal(self):
        cmd = build_chrome_command(
            Path("/usr/bin/chrome"), "https://example.com",
            user_data_dir=None, profile_directory=None, new_window=False,
        )
        assert cmd == ["/usr/bin/chrome", "https://example.com"]

    def test_all_options(self, tmp_path):
        udd = tmp_path / "profile"
        cmd = build_chrome_command(
            Path("/usr/bin/chrome"), "https://example.com",
            user_data_dir=udd, profile_directory="Profile 1", new_window=True,
        )
        assert cmd == [
            "/usr/bin/chrome",
            f"--user-data-dir={udd}",
            "--profile-directory=Profile 1",
            "--new-window",
            "https://example.com",
        ]
