"""login_helper のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sf_session.login_helper import (
    LoginExhaustedError,
    MfaTimeoutError,
    ensure_logged_in,
    wait_until_logged_in,
)

MODULE = "sf_session.login_helper"


def _make_driver(**overrides) -> MagicMock:
    """テスト用の mock WebDriver を生成。"""
    driver = MagicMock()
    driver.current_url = overrides.get("current_url", "https://example.salesforce.com/home")
    return driver


# ── wait_until_logged_in ──────────────────────────────────


class TestWaitUntilLoggedIn:
    def test_timeout_raises_mfa_timeout_error(self):
        """timeout 超過で MfaTimeoutError が raise される。"""
        driver = _make_driver()

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.is_login_page", return_value=False),
            patch(f"{MODULE}.time.sleep"),
            pytest.raises(MfaTimeoutError, match="タイムアウト"),
        ):
            wait_until_logged_in(driver, poll=1.0, timeout=3)

    def test_login_page_detected_raises_mfa_timeout_error(self):
        """poll 中に login page に戻されたら MfaTimeoutError。"""
        driver = _make_driver()

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.is_login_page", return_value=True),
            patch(f"{MODULE}.time.sleep"),
            pytest.raises(MfaTimeoutError, match="login page"),
        ):
            wait_until_logged_in(driver, poll=1.0, timeout=60)

    def test_success_returns_normally(self):
        """is_logged_in が True を返せば正常終了。"""
        driver = _make_driver()
        call_count = {"n": 0}

        def logged_in_after_2(_driver):
            call_count["n"] += 1
            return call_count["n"] >= 2

        with (
            patch(f"{MODULE}.is_logged_in", side_effect=logged_in_after_2),
            patch(f"{MODULE}.time.sleep"),
        ):
            # 例外なく完了すれば OK
            wait_until_logged_in(driver, poll=1.0, timeout=60)

    def test_off_sf_domain_raises_mfa_timeout_error(self):
        """SF ドメイン外に長時間いると MfaTimeoutError (認証キャンセル検出)。"""
        driver = _make_driver(current_url="https://sso.example.com/error")

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.is_login_page", return_value=False),
            patch(f"{MODULE}.is_mfa_page", return_value=False),
            patch(f"{MODULE}.time.sleep"),
            pytest.raises(MfaTimeoutError, match="SF ドメインへの遷移なし"),
        ):
            wait_until_logged_in(driver, poll=1.0, timeout=600)

    def test_keyboard_interrupt_propagates(self):
        """Ctrl+C は KeyboardInterrupt としてそのまま propagate。"""
        driver = _make_driver()

        def sleep_raises(_seconds):
            raise KeyboardInterrupt

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.time.sleep", side_effect=sleep_raises),
            pytest.raises(KeyboardInterrupt),
        ):
            wait_until_logged_in(driver, poll=1.0, timeout=60)


# ── ensure_logged_in ──────────────────────────────────────


class TestEnsureLoggedIn:
    def test_already_logged_in_returns_false(self):
        """既にログイン済みなら False を返して何もしない。"""
        driver = _make_driver()

        with patch(f"{MODULE}.is_logged_in", return_value=True):
            result = ensure_logged_in(driver, "user", "pass")

        assert result is False

    def test_mfa_timeout_then_retry_succeeds(self):
        """1回目 MFA timeout → 2回目で成功。"""
        driver = _make_driver()
        attempt = {"n": 0}

        def mock_wait(*args, **kwargs):
            attempt["n"] += 1
            if attempt["n"] == 1:
                raise MfaTimeoutError("timeout")
            # 2回目は成功（何もしない）

        with (
            patch(f"{MODULE}.is_logged_in", side_effect=[
                False,   # ensure_logged_in 冒頭の check
                False,   # 1回目 loop: is_mfa_page の elif
                False,   # 2回目 loop 冒頭で is_login_page の前の check ではない
                True,    # 2回目 loop 終了後のチェック（is_logged_in は wait 内で True）
            ]),
            patch(f"{MODULE}.is_login_page", return_value=True),
            patch(f"{MODULE}.is_mfa_page", return_value=False),
            patch(f"{MODULE}.fill_credentials"),
            patch(f"{MODULE}.wait_page_load"),
            patch(f"{MODULE}.wait_until_logged_in", side_effect=mock_wait),
        ):
            result = ensure_logged_in(driver, "user", "pass", max_retries=2)

        assert result is True
        assert attempt["n"] == 2

    def test_all_retries_exhausted_raises(self):
        """全 retry 消費で LoginExhaustedError。"""
        driver = _make_driver()

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.is_login_page", return_value=True),
            patch(f"{MODULE}.is_mfa_page", return_value=False),
            patch(f"{MODULE}.fill_credentials"),
            patch(f"{MODULE}.wait_page_load"),
            patch(
                f"{MODULE}.wait_until_logged_in",
                side_effect=MfaTimeoutError("timeout"),
            ),
            pytest.raises(LoginExhaustedError, match="retry 回数上限"),
        ):
            ensure_logged_in(driver, "user", "pass", max_retries=2)
