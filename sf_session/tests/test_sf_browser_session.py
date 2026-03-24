"""sf_browser_session のテスト。"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from sf_session.sf_browser_session import (
    BrowserSession,
    close_browser_session,
    prepare_salesforce_session,
)


class TestBrowserSession:
    def test_self_launched_true(self):
        driver = MagicMock()
        proc = MagicMock(spec=subprocess.Popen)
        session = BrowserSession(driver=driver, chrome_proc=proc)
        assert session.self_launched is True

    def test_self_launched_false(self):
        driver = MagicMock()
        session = BrowserSession(driver=driver)
        assert session.self_launched is False

    def test_self_launched_none(self):
        driver = MagicMock()
        session = BrowserSession(driver=driver, chrome_proc=None)
        assert session.self_launched is False


class TestPrepareSalesforceSession:
    @patch("sf_session.sf_browser_session.ensure_logged_in")
    @patch("sf_session.sf_browser_session.wait_page_load")
    @patch("sf_session.sf_browser_session.try_connect_driver")
    def test_existing_connection(self, mock_try, mock_wait, mock_login):
        """既存 Chrome に接続成功するケース。"""
        mock_driver = MagicMock()
        mock_try.return_value = mock_driver

        session = prepare_salesforce_session(try_existing=True)

        assert session.driver is mock_driver
        assert session.chrome_proc is None
        assert not session.self_launched
        mock_driver.get.assert_called_once()
        mock_wait.assert_called_once_with(mock_driver)
        mock_login.assert_called_once_with(mock_driver)

    @patch("sf_session.sf_browser_session.ensure_logged_in")
    @patch("sf_session.sf_browser_session.wait_page_load")
    @patch("sf_session.sf_browser_session.connect_driver")
    @patch("sf_session.sf_browser_session.launch_chrome")
    @patch("sf_session.sf_browser_session.try_connect_driver", return_value=None)
    @patch("sf_session.sf_browser_session.time.sleep")
    def test_launch_chrome(
        self, mock_sleep, mock_try, mock_launch, mock_connect,
        mock_wait, mock_login,
    ):
        """既存接続失敗 → Chrome 起動するケース。"""
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_launch.return_value = mock_proc
        mock_driver = MagicMock()
        mock_connect.return_value = mock_driver

        session = prepare_salesforce_session(
            user_data_dir="/tmp/profile", try_existing=True,
        )

        assert session.driver is mock_driver
        assert session.chrome_proc is mock_proc
        assert session.self_launched
        mock_launch.assert_called_once()
        # self_launched なので navigate skip
        mock_driver.get.assert_not_called()
        mock_wait.assert_called_once_with(mock_driver)

    @patch("sf_session.sf_browser_session.try_connect_driver", return_value=None)
    def test_no_user_data_dir_raises(self, mock_try):
        """user_data_dir=None で既存接続も失敗すると RuntimeError。"""
        with pytest.raises(RuntimeError, match="user_data_dir 未指定"):
            prepare_salesforce_session(
                user_data_dir=None, try_existing=True,
            )

    @patch("sf_session.sf_browser_session.connect_driver")
    @patch("sf_session.sf_browser_session.launch_chrome")
    @patch("sf_session.sf_browser_session.try_connect_driver", return_value=None)
    @patch("sf_session.sf_browser_session.time.sleep")
    def test_connect_failure_terminates_chrome(
        self, mock_sleep, mock_try, mock_launch, mock_connect,
    ):
        """connect_driver 失敗時に Chrome を terminate する。"""
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 99999
        mock_proc.poll.return_value = None
        mock_launch.return_value = mock_proc
        mock_connect.side_effect = Exception("connection failed")

        with pytest.raises(Exception, match="connection failed"):
            prepare_salesforce_session(
                user_data_dir="/tmp/profile", try_existing=True,
            )

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()

    @patch("sf_session.sf_browser_session.ensure_logged_in")
    @patch("sf_session.sf_browser_session.wait_page_load")
    @patch("sf_session.sf_browser_session.connect_driver")
    @patch("sf_session.sf_browser_session.launch_chrome")
    @patch("sf_session.sf_browser_session.time.sleep")
    def test_try_existing_false_skips_try_connect(
        self, mock_sleep, mock_launch, mock_connect,
        mock_wait, mock_login,
    ):
        """try_existing=False なら try_connect_driver を呼ばない。"""
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_launch.return_value = mock_proc
        mock_driver = MagicMock()
        mock_connect.return_value = mock_driver

        with patch(
            "sf_session.sf_browser_session.try_connect_driver"
        ) as mock_try:
            session = prepare_salesforce_session(
                user_data_dir="/tmp/profile", try_existing=False,
            )
            mock_try.assert_not_called()

        assert session.self_launched

    @patch("sf_session.sf_browser_session.ensure_logged_in")
    @patch("sf_session.sf_browser_session.wait_page_load")
    @patch("sf_session.sf_browser_session.connect_driver")
    @patch("sf_session.sf_browser_session.launch_chrome")
    @patch("sf_session.sf_browser_session.try_connect_driver", return_value=None)
    @patch("sf_session.sf_browser_session.time.sleep")
    def test_login_failure_cleans_up_chrome(
        self, mock_sleep, mock_try, mock_launch, mock_connect,
        mock_wait, mock_login,
    ):
        """ensure_logged_in 失敗時に Chrome process を cleanup する。"""
        from sf_session.login_helper import LoginExhaustedError

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 11111
        mock_proc.poll.return_value = None
        mock_launch.return_value = mock_proc
        mock_driver = MagicMock()
        mock_connect.return_value = mock_driver
        mock_login.side_effect = LoginExhaustedError("login failed")

        with pytest.raises(LoginExhaustedError):
            prepare_salesforce_session(
                user_data_dir="/tmp/profile", try_existing=True,
            )

        # driver.quit + chrome_proc.terminate が呼ばれている
        mock_driver.quit.assert_called_once()
        mock_proc.terminate.assert_called_once()

    @patch("sf_session.sf_browser_session.wait_page_load")
    @patch("sf_session.sf_browser_session.try_connect_driver")
    def test_login_failure_existing_chrome_quits_driver(
        self, mock_try, mock_wait,
    ):
        """既存 Chrome 接続で ensure_logged_in 失敗 → driver.quit される。"""
        from sf_session.login_helper import LoginExhaustedError

        mock_driver = MagicMock()
        mock_try.return_value = mock_driver
        with patch(
            "sf_session.sf_browser_session.ensure_logged_in",
            side_effect=LoginExhaustedError("expired"),
        ):
            with pytest.raises(LoginExhaustedError):
                prepare_salesforce_session(try_existing=True)

        mock_driver.quit.assert_called_once()


class TestCloseBrowserSession:
    def test_quit_and_terminate(self):
        """driver.quit + chrome_proc terminate が呼ばれる。"""
        driver = MagicMock()
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345
        proc.poll.return_value = None
        session = BrowserSession(driver=driver, chrome_proc=proc)

        close_browser_session(session)

        driver.quit.assert_called_once()
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once()

    def test_no_chrome_proc(self):
        """chrome_proc=None のケースでも driver.quit は呼ばれる。"""
        driver = MagicMock()
        session = BrowserSession(driver=driver)

        close_browser_session(session)

        driver.quit.assert_called_once()

    def test_driver_quit_exception_ignored(self):
        """driver.quit() が例外を出しても chrome_proc の cleanup は続行。"""
        driver = MagicMock()
        driver.quit.side_effect = Exception("already closed")
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 99999
        proc.poll.return_value = None
        session = BrowserSession(driver=driver, chrome_proc=proc)

        close_browser_session(session)

        proc.terminate.assert_called_once()
