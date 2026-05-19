"""Optional browser backend adapter for Playwright-compatible browsers."""

from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import Browser, sync_playwright

from utils import settings


def _configured_backend() -> str:
    config = settings.config if isinstance(settings.config, dict) else {}
    browser_config = config.get("settings", {}).get("browser", {})
    return str(browser_config.get("backend", "playwright")).casefold()


@contextmanager
def launch_browser(headless: bool = True) -> Iterator[Browser]:
    """Launch the configured browser backend.

    Defaults to stock Playwright. CloakBrowser is opt-in via
    settings.browser.backend = "cloakbrowser" and returns a Playwright-compatible
    Browser object, preserving browser.new_context(...) call sites.
    """
    backend = _configured_backend()

    if backend == "cloakbrowser":
        import cloakbrowser

        browser = cloakbrowser.launch(headless=headless, humanize=True)
        try:
            yield browser
        finally:
            browser.close()
        return

    if backend != "playwright":
        raise ValueError(
            f"Unsupported browser backend '{backend}'. Use 'playwright' or 'cloakbrowser'."
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            yield browser
        finally:
            browser.close()