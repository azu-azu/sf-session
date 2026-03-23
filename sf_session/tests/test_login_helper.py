"""login_helper のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sf_session.login_helper import (
    AuthFlowLeftError,
    LoginExhaustedError,
    LoginPageReturnedError,
    MfaTimeoutError,
    ensure_logged_in,
    is_sso_page,
    wait_until_logged_in,
)

MODULE = "sf_session.login_helper"


def _make_driver(**overrides) -> MagicMock:
    """テスト用の mock WebDriver を生成。"""
    driver = MagicMock()
    driver.current_url = overrides.get("current_url", "https://example.salesforce.com/home")
    return driver


# ── is_sso_page ──────────────────────────────────────────


class TestIsSsoPage:
    def test_sso_url_detected(self):
        driver = _make_driver(current_url="https://company.sso~long-hash.example.com/login")
        assert is_sso_page(driver) is True

    def test_sf_domain_not_sso(self):
        driver = _make_driver(current_url="https://example.salesforce.com/home")
        assert is_sso_page(driver) is False

    def test_sso_in_path(self):
        driver = _make_driver(current_url="https://auth.example.com/sso/callback")
        assert is_sso_page(driver) is True


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

    def test_login_page_returned_after_leaving(self):
        """login page を離れてから戻されたら LoginPageReturnedError。"""
        driver = _make_driver()
        call_count = {"n": 0}

        def is_login_side_effect(_driver):
            call_count["n"] += 1
            # 1回目: login page ではない (SSO 等) → seen_non_login = True
            # 2回目: login page に戻された → error
            return call_count["n"] >= 2

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.is_login_page", side_effect=is_login_side_effect),
            patch(f"{MODULE}.time.sleep"),
            pytest.raises(LoginPageReturnedError, match="login page"),
        ):
            wait_until_logged_in(driver, poll=1.0, timeout=60)

    def test_initial_login_page_waits_without_error(self):
        """初回表示が login page なら error にせず timeout まで待機する。"""
        driver = _make_driver()

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.is_login_page", return_value=True),
            patch(f"{MODULE}.time.sleep"),
            pytest.raises(MfaTimeoutError),
        ):
            wait_until_logged_in(driver, poll=1.0, timeout=3)

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

    def test_off_sf_domain_raises_auth_flow_left_error(self):
        """SF ドメイン外に長時間いると AuthFlowLeftError (認証キャンセル検出)。"""
        driver = _make_driver(current_url="https://other.example.com/error")

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.is_login_page", return_value=False),
            patch(f"{MODULE}.is_mfa_page", return_value=False),
            patch(f"{MODULE}.time.sleep"),
            pytest.raises(AuthFlowLeftError, match="認証フロー外に遷移"),
        ):
            wait_until_logged_in(driver, poll=1.0, timeout=600)

    def test_sso_domain_resets_off_sf_timer(self):
        """SSO ドメインにいる間は elapsed_off_sf がリセットされる。"""
        driver = _make_driver(current_url="https://company.sso~hash.example.com/auth")
        call_count = {"n": 0}

        def logged_in_after_3(_driver):
            call_count["n"] += 1
            return call_count["n"] >= 3

        with (
            patch(f"{MODULE}.is_logged_in", side_effect=logged_in_after_3),
            patch(f"{MODULE}.is_login_page", return_value=False),
            patch(f"{MODULE}.is_mfa_page", return_value=False),
            patch(f"{MODULE}.time.sleep"),
        ):
            # SSO domain → is_sso_page=True → elapsed_off_sf reset → no timeout
            wait_until_logged_in(driver, poll=1.0, timeout=60)

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
            result = ensure_logged_in(driver)

        assert result is False

    def test_manual_login_wait_succeeds(self):
        """手動ログイン待機 → ログイン完了で True を返す。"""
        driver = _make_driver()

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.wait_until_logged_in"),
        ):
            result = ensure_logged_in(driver)

        assert result is True

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
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.wait_until_logged_in", side_effect=mock_wait),
        ):
            result = ensure_logged_in(driver, max_retries=2)

        assert result is True
        assert attempt["n"] == 2

    def test_all_retries_exhausted_raises(self):
        """全 retry 消費で LoginExhaustedError。"""
        driver = _make_driver()

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(
                f"{MODULE}.wait_until_logged_in",
                side_effect=MfaTimeoutError("timeout"),
            ),
            pytest.raises(LoginExhaustedError, match="retry 回数上限"),
        ):
            ensure_logged_in(driver, max_retries=2)

    def test_auth_flow_left_no_retry(self):
        """AuthFlowLeftError は retry せず即 LoginExhaustedError。"""
        driver = _make_driver()
        call_count = {"n": 0}

        def mock_wait(*args, **kwargs):
            call_count["n"] += 1
            raise AuthFlowLeftError("認証フロー外に遷移")

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.wait_until_logged_in", side_effect=mock_wait),
            pytest.raises(LoginExhaustedError, match="認証フロー外に遷移"),
        ):
            ensure_logged_in(driver, max_retries=3)

        # retry せず1回で打ち切り
        assert call_count["n"] == 1

    def test_login_page_returned_no_retry(self):
        """LoginPageReturnedError は retry せず即 LoginExhaustedError。"""
        driver = _make_driver()
        call_count = {"n": 0}

        def mock_wait(*args, **kwargs):
            call_count["n"] += 1
            raise LoginPageReturnedError("login page へ戻された")

        with (
            patch(f"{MODULE}.is_logged_in", return_value=False),
            patch(f"{MODULE}.wait_until_logged_in", side_effect=mock_wait),
            pytest.raises(LoginExhaustedError, match="login page へ戻された"),
        ):
            ensure_logged_in(driver, max_retries=3)

        assert call_count["n"] == 1
