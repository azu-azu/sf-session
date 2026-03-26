"""download のテスト (thin orchestration / parse_args / main integration)。"""

from __future__ import annotations

from sf_session.config import CHROME_EXE_PATH, CHROME_USER_DATA_DIR
from sf_session.download import (
    main,
    parse_args,
)
from sf_session.download_runner import (
    DEFAULT_POLL,
    DEFAULT_TIMEOUT,
    DEFAULT_INTERVAL,
)
from sf_session.browser import REMOTE_DEBUGGING_PORT

from sf_session.tests.helpers import make_job


class TestParseArgs:
    def test_override_chrome_path(self):
        args = parse_args(["--chrome-path", "/usr/bin/chrome"])
        assert args.chrome_path == "/usr/bin/chrome"

    def test_default_chrome_path(self):
        args = parse_args([])
        assert args.chrome_path == CHROME_EXE_PATH

    def test_defaults(self):
        args = parse_args([])
        assert args.timeout == DEFAULT_TIMEOUT
        assert args.poll == DEFAULT_POLL
        assert args.interval == DEFAULT_INTERVAL
        assert not args.date_suffix
        assert not args.dry_run
        assert not args.direct_deliver
        assert not args.my_chrome
        assert not args.ids_file
        assert args.user_data_dir == CHROME_USER_DATA_DIR
        assert args.profile_directory is None
        assert args.port == REMOTE_DEBUGGING_PORT
        assert not args.no_login_check
        assert not args.force
        assert not args.open_download_dir
        assert not args.open_output_dir

    def test_all_flags(self):
        args = parse_args([
            "--chrome-path", "chrome",
            "--download-dir", "/tmp/dl",
            "--timeout", "30",
            "--poll", "0.5",
            "--date-suffix",
            "--interval", "5.0",
            "--direct-deliver",
            "--ids-file",
            "--dry-run",
            "--my-chrome",
            "--user-data-dir", CHROME_USER_DATA_DIR,
            "--profile-directory", "Profile 1",
            "--port", "9333",
            "--no-login-check",
            "--force",
            "--open-download-dir",
            "--open-output-dir",
        ])
        assert args.download_dir == "/tmp/dl"
        assert args.timeout == 30
        assert args.poll == 0.5
        assert args.date_suffix
        assert args.interval == 5.0
        assert args.direct_deliver
        assert args.ids_file
        assert args.dry_run
        assert args.my_chrome
        assert args.user_data_dir == CHROME_USER_DATA_DIR
        assert args.profile_directory == "Profile 1"
        assert args.port == 9333
        assert args.no_login_check
        assert args.force
        assert args.open_download_dir
        assert args.open_output_dir


# ── helper: main() の外部依存を全て stub する fixture ──────────

def _stub_main_externals(monkeypatch, tmp_path, *, jobs=None):
    """main() を軽量に実行するための monkeypatch 群。

    Returns (staging_dir, download_dir) の tuple。
    """
    staging_dir = tmp_path / "outputs_csv"
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    chrome_path = tmp_path / "chrome"
    chrome_path.touch()

    if jobs is None:
        jobs = [make_job(no="1", report_id="00O001")]

    downloaded = download_dir / "report.csv"
    downloaded.write_text("data")

    monkeypatch.setattr("sf_session.download.CSV_STAGING_DIR", staging_dir)
    monkeypatch.setattr("sf_session.download.CHROME_EXE_PATH", str(chrome_path))
    monkeypatch.setattr(
        "sf_session.download_outputs.OUTPUT_RESULTS_DIR", tmp_path / "results",
    )
    monkeypatch.setattr(
        "sf_session.download.load_active_jobs", lambda *a, **kw: jobs,
    )
    monkeypatch.setattr(
        "sf_session.download.resolve_download_dir", lambda x: download_dir,
    )
    monkeypatch.setattr("sf_session.download.ensure_exists", lambda *a: None)
    monkeypatch.setattr(
        "sf_session.download_runner.snapshot_files", lambda *a, **kw: {},
    )
    monkeypatch.setattr(
        "sf_session.download_runner.subprocess.Popen", lambda cmd: None,
    )
    monkeypatch.setattr(
        "sf_session.download_runner.wait_for_new_download",
        lambda *a, **kw: downloaded,
    )
    monkeypatch.setattr(
        "sf_session.download.should_run_download", lambda *a: (True, "weekday"),
    )
    monkeypatch.setattr(
        "sf_session.download.probe_output_dir", lambda *a: None,
    )

    return staging_dir, download_dir


class TestWorkDirSwap:
    """work_dir → CSV_STAGING_DIR への atomic swap テスト。"""

    def test_swap_creates_staging_dir(self, tmp_path, monkeypatch):
        """正常終了時、work_dir が CSV_STAGING_DIR に rename される。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)

        rc = main(["--no-login-check", "--force"])

        assert rc == 0
        assert staging_dir.is_dir()
        # work_dir は swap 後に消えている
        assert not list(tmp_path.glob(f"{staging_dir.name}_work_*"))

    def test_swap_creates_prev_backup(self, tmp_path, monkeypatch):
        """既存 staging_dir がある場合、_prev_{ts} に退避される。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)

        # 前回分を staging_dir に準備
        staging_dir.mkdir(parents=True)
        prev_file = staging_dir / "old_report.csv"
        prev_file.write_text("old data")

        rc = main(["--no-login-check", "--force"])

        assert rc == 0
        prevs = list(tmp_path.glob(f"{staging_dir.name}_prev_*"))
        assert len(prevs) == 1
        assert (prevs[0] / "old_report.csv").read_text() == "old data"
        # 新しい staging_dir には今回のファイルがある
        assert staging_dir.is_dir()

    def test_prev_limited_to_two_generations(self, tmp_path, monkeypatch):
        """古い _prev_* は swap 前に削除され、2世代 (current + prev) に制限される。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)

        # 古い _prev_*
        old_prev = tmp_path / f"{staging_dir.name}_prev_20260101_000000"
        old_prev.mkdir(parents=True)
        (old_prev / "ancient.csv").write_text("ancient")

        # 前回分
        staging_dir.mkdir(parents=True)
        (staging_dir / "old_report.csv").write_text("old")

        rc = main(["--no-login-check", "--force"])

        assert rc == 0
        prevs = list(tmp_path.glob(f"{staging_dir.name}_prev_*"))
        # 古い prev は消え、今回の prev だけ残る
        assert len(prevs) == 1
        assert (prevs[0] / "old_report.csv").exists()
        assert not (prevs[0] / "ancient.csv").exists()

    def test_exception_keeps_current_intact(self, tmp_path, monkeypatch):
        """export 中に exception が発生しても、現行 staging_dir は残る。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)

        # 前回分を staging_dir に準備
        staging_dir.mkdir(parents=True)
        (staging_dir / "precious.csv").write_text("do not lose")

        # export_batch を exception で終了させる
        monkeypatch.setattr(
            "sf_session.download.export_batch",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        try:
            main(["--no-login-check", "--force"])
        except RuntimeError:
            pass

        # current はそのまま残っている
        assert (staging_dir / "precious.csv").read_text() == "do not lose"
        # work_dir は cleanup されている
        assert not list(tmp_path.glob(f"{staging_dir.name}_work_*"))

    def test_direct_deliver_skips_swap(self, tmp_path, monkeypatch):
        """--direct-deliver 時は work_dir / swap を使わない。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)

        rc = main(["--no-login-check", "--direct-deliver", "--force"])

        assert rc == 0
        # staging_dir も work_dir も作成されない
        assert not list(tmp_path.glob(f"{staging_dir.name}_work_*"))

    def test_zero_success_no_swap(self, tmp_path, monkeypatch):
        """全件失敗時は swap せず、前回の current を保持する。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)

        # 前回分を staging_dir に準備
        staging_dir.mkdir(parents=True)
        (staging_dir / "good_report.csv").write_text("previous good data")

        # 全件 timeout させる
        monkeypatch.setattr(
            "sf_session.download_runner.wait_for_new_download",
            lambda *a, **kw: (_ for _ in ()).throw(TimeoutError("timeout")),
        )

        rc = main(["--no-login-check", "--force"])

        assert rc == 1
        # current は前回分がそのまま
        assert (staging_dir / "good_report.csv").read_text() == "previous good data"
        # work_dir は cleanup されている
        assert not list(tmp_path.glob(f"{staging_dir.name}_work_*"))

    def test_marker_written_to_final_staging_dir(self, tmp_path, monkeypatch):
        """完了マーカーは work_dir に書かれてから swap で CSV_STAGING_DIR に入る。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)

        rc = main(["--no-login-check", "--force"])

        assert rc == 0
        markers = [f for f in staging_dir.iterdir() if "成功" in f.name]
        assert len(markers) == 1


class TestBusinessDayGuard:
    """営業日ガードのテスト。"""

    def test_non_business_day_skip(self, tmp_path, monkeypatch):
        """非営業日は skip して return 0。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "sf_session.download.should_run_download",
            lambda *a: (False, "weekend"),
        )

        rc = main(["--no-login-check"])

        assert rc == 0
        # export 実行されず staging_dir は作られない
        assert not staging_dir.exists()

    def test_force_overrides_business_day(self, tmp_path, monkeypatch):
        """--force で営業日チェックを bypass。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "sf_session.download.should_run_download",
            lambda *a: (False, "weekend"),
        )

        rc = main(["--no-login-check", "--force"])

        assert rc == 0
        assert staging_dir.is_dir()


class TestPreflightFailFast:
    """pre-flight login check が fail-fast するテスト。"""

    def test_preflight_failure_returns_1(self, tmp_path, monkeypatch):
        """pre-flight 失敗で return 1 (続行しない)。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "sf_session.download.prepare_salesforce_session",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("Chrome 起動失敗")),
        )

        # --no-login-check なし → pre-flight 実行 → 失敗 → return 1
        rc = main(["--force"])

        assert rc == 1
        # export は実行されてない（work_dir に何も入ってない or swap されてない）

    def test_no_login_check_skips_preflight(self, tmp_path, monkeypatch):
        """--no-login-check なら pre-flight を skip して export は実行される。"""
        staging_dir, _ = _stub_main_externals(monkeypatch, tmp_path)

        rc = main(["--no-login-check", "--force"])

        assert rc == 0
        assert staging_dir.is_dir()
