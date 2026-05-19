import sys
from types import SimpleNamespace

from utils import settings


class FakeBrowser:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_launch_browser_defaults_to_playwright(monkeypatch):
    from utils import browser_backend

    fake_browser = FakeBrowser()

    class FakePlaywrightContext:
        def __enter__(self):
            return SimpleNamespace(
                chromium=SimpleNamespace(launch=lambda headless: fake_browser)
            )

        def __exit__(self, exc_type, exc, traceback):
            return False

    settings.config = {"settings": {}}
    monkeypatch.setattr(browser_backend, "sync_playwright", lambda: FakePlaywrightContext())

    with browser_backend.launch_browser() as browser:
        assert browser is fake_browser

    assert fake_browser.closed is True


def test_launch_browser_uses_cloakbrowser_when_configured(monkeypatch):
    from utils import browser_backend

    fake_browser = FakeBrowser()
    launch_calls = []
    fake_module = SimpleNamespace(
        launch=lambda **kwargs: launch_calls.append(kwargs) or fake_browser
    )

    settings.config = {"settings": {"browser": {"backend": "cloakbrowser"}}}
    monkeypatch.setitem(sys.modules, "cloakbrowser", fake_module)

    with browser_backend.launch_browser(headless=False) as browser:
        assert browser is fake_browser

    assert launch_calls == [{"headless": False, "humanize": True}]
    assert fake_browser.closed is True