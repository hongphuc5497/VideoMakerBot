from unittest.mock import MagicMock, patch

from playwright.sync_api import TimeoutError

from platforms.threads import auth
from platforms.threads.auth import _is_logged_in_threads_url


def test_logged_in_threads_url_accepts_current_threads_com_home():
    assert _is_logged_in_threads_url("https://www.threads.com/") is True
    assert _is_logged_in_threads_url("https://www.threads.com/?hl=en") is True


def test_logged_in_threads_url_accepts_legacy_threads_net_home():
    assert _is_logged_in_threads_url("https://www.threads.net/") is True


def test_logged_in_threads_url_rejects_login_page_and_other_hosts():
    assert _is_logged_in_threads_url("https://www.threads.com/login") is False
    assert _is_logged_in_threads_url("https://www.threads.net/login") is False
    assert _is_logged_in_threads_url("https://example.com/") is False


def test_logged_in_threads_url_rejects_checkpoint_and_challenge_paths():
    assert _is_logged_in_threads_url("https://www.threads.com/challenge/") is False
    assert _is_logged_in_threads_url("https://www.threads.net/checkpoint/") is False
    assert _is_logged_in_threads_url("https://www.threads.com/consent/") is False


def test_logged_in_threads_url_requires_https():
    assert _is_logged_in_threads_url("http://www.threads.com/") is False


def test_login_to_threads_retries_with_enter_when_button_click_times_out(tmp_path):
    username_input = MagicMock()
    password_input = MagicMock()
    login_button = MagicMock()
    login_button.click.side_effect = TimeoutError("button click timed out")
    role_result = MagicMock()
    role_result.first = login_button

    page = MagicMock()
    page.locator.side_effect = lambda selector: username_input if "username" in selector else password_input
    page.get_by_role.return_value = role_result

    context = MagicMock()
    context.cookies.return_value = [{"name": "sessionid", "value": "ok"}]

    cookie_path = tmp_path / "cookie-threads.json"

    with patch.object(auth.settings, "config", {"threads": {"creds": {"username": "demo", "password": "secret"}}}), \
         patch.object(auth, "THREADS_COOKIE_FILE", str(cookie_path)):
        auth.login_to_threads(page, context)

    username_input.fill.assert_called_once_with("demo")
    password_input.fill.assert_called_once_with("secret")
    password_input.press.assert_called_once_with("Enter")
    assert page.wait_for_url.call_count == 1
    assert cookie_path.exists()