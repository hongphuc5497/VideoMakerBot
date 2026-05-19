"""Shared Playwright authentication for Threads.

Used by both the screenshotter (screenshot.py) and the web scraper (scraper.py).
"""

import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Browser, BrowserContext, Page, TimeoutError, ViewportSize

from utils import settings
from utils.console import emit_scraper_event, print_substep

THREADS_LOGIN_URL = "https://www.threads.com/login"
THREADS_COOKIE_FILE = "./video_creation/data/cookie-threads.json"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
THREADS_HOSTS = {
    "threads.com",
    "www.threads.com",
    "threads.net",
    "www.threads.net",
}
THREADS_NON_AUTH_PATH_PREFIXES = (
    "/login",
    "/challenge",
    "/checkpoint",
    "/consent",
    "/accountsuspended",
    "/suspended",
)


def _is_logged_in_threads_url(url: str) -> bool:
    """Return True once Threads has navigated away from the login page."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    path = (parsed.path or "/").lower()
    return parsed.scheme == "https" and hostname in THREADS_HOSTS and not any(
        path.startswith(prefix) for prefix in THREADS_NON_AUTH_PATH_PREFIXES
    )


def login_to_threads(page: Page, _context: BrowserContext) -> None:
    """Log into Threads via Instagram credentials and persist session cookies."""
    username = settings.config["threads"]["creds"].get("username", "").strip()
    password = settings.config["threads"]["creds"].get("password", "").strip()

    if not username or not password:
        raise RuntimeError(
            "Threads login requires credentials. "
            "Set threads.creds.username and threads.creds.password in config.toml"
        )

    print_substep("Logging into Threads (via Instagram)...")
    emit_scraper_event("login", {"message": "Logging into Threads (via Instagram)..."})
    page.goto(THREADS_LOGIN_URL, timeout=0)
    page.wait_for_load_state("domcontentloaded")

    username_input = page.locator('input[autocomplete="username"]')
    password_input = page.locator('input[autocomplete="current-password"]')
    username_input.fill(username)
    password_input.fill(password)

    # CloakBrowser can be slightly flaky with the humanized button click even
    # when the credentials are correct. Try the visible login button first,
    # then fall back to pressing Enter in the password field.
    submit_attempts = [
        ("button click", lambda: page.get_by_role("button", name="Log in", exact=True).first.click()),
        ("password Enter", lambda: password_input.press("Enter")),
    ]
    last_error = None
    for index, (label, submit) in enumerate(submit_attempts):
        try:
            submit()
            # Threads currently redirects to threads.com on successful login,
            # but older saved sessions and some flows may still hit threads.net.
            page.wait_for_url(_is_logged_in_threads_url, timeout=30000 if index == 0 else 15000)
            break
        except TimeoutError as error:
            last_error = error
            if index == len(submit_attempts) - 1:
                raise
            print_substep(f"Threads login via {label} timed out. Retrying...", style="yellow")

    page.wait_for_load_state("domcontentloaded")

    cookies = _context.cookies()
    Path(THREADS_COOKIE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(THREADS_COOKIE_FILE, "w") as f:
        json.dump(cookies, f)

    print_substep("Logged into Threads and saved session cookies.", style="bold green")
    emit_scraper_event("login", {"message": "Logged in successfully"})


def ensure_authenticated_context(browser: Browser, **kwargs) -> BrowserContext:
    """Create a Playwright browser context with Threads session cookies loaded.

    Loads saved cookies from cookie-threads.json. If no valid session exists,
    performs a fresh login and persists the cookies.

    Keyword arguments override defaults for locale, viewport, device_scale_factor,
    color_scheme, and user_agent.
    """
    theme = settings.config["settings"]["theme"]
    W = int(settings.config["settings"]["resolution_w"])
    H = int(settings.config["settings"]["resolution_h"])
    dsf = (W // 600) + 1

    defaults = {
        "locale": "en-US",
        "color_scheme": "dark" if theme == "dark" else "light",
        "viewport": ViewportSize(width=W, height=H),
        "device_scale_factor": dsf,
        "user_agent": DEFAULT_USER_AGENT,
    }
    defaults.update(kwargs)

    context = browser.new_context(**defaults)

    cookie_path = Path(THREADS_COOKIE_FILE)
    if cookie_path.exists():
        try:
            with open(cookie_path, encoding="utf-8") as f:
                saved_cookies = json.load(f)
            context.add_cookies(saved_cookies)
            print_substep("Loaded saved Threads session cookies.")
            emit_scraper_event("login", {"message": "Loaded saved session cookies"})
        except (json.JSONDecodeError, IOError):
            print_substep("Saved cookies corrupted. Logging in fresh...")
            page = context.new_page()
            login_to_threads(page, context)
            page.close()
    else:
        print_substep("No saved cookies found. Logging in...")
        page = context.new_page()
        login_to_threads(page, context)
        page.close()

    return context
