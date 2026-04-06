"""Captures screenshots of Threads posts via Playwright."""

import json
import re
from pathlib import Path
from typing import Final

from playwright.sync_api import ViewportSize, sync_playwright

from utils import settings
from utils.console import print_step, print_substep


THREADS_LOGIN_URL = "https://www.threads.net/login"
THREADS_COOKIE_FILE = "./video_creation/data/cookie-threads.json"


def _login_to_threads(page, context) -> None:
    """
    Performs Threads login via Instagram credentials (Threads uses Instagram auth).
    Saves session cookies to cookie-threads.json for reuse on future runs.

    Args:
        page: Playwright page object
        context: Playwright browser context

    Raises:
        RuntimeError: If login credentials are not configured.
    """
    username = settings.config["threads"]["creds"].get("username", "").strip()
    password = settings.config["threads"]["creds"].get("password", "").strip()

    if not username or not password:
        raise RuntimeError(
            "Threads screenshot login requires credentials. "
            "Set threads.creds.username and threads.creds.password in config.toml"
        )

    print_substep("Logging into Threads (via Instagram)...")
    page.goto(THREADS_LOGIN_URL, timeout=0)
    page.wait_for_load_state("networkidle")

    # Threads login form uses Instagram auth with these selectors
    page.locator('input[autocomplete="username"]').fill(username)
    page.locator('input[autocomplete="current-password"]').fill(password)
    page.get_by_role("button", name="Log in").click()

    # Wait for login to complete
    page.wait_for_timeout(6000)

    # Persist cookies for reuse
    cookies = context.cookies()
    Path(THREADS_COOKIE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(THREADS_COOKIE_FILE, "w") as f:
        json.dump(cookies, f)

    print_substep("Logged into Threads and saved session cookies.", style="bold green")


def get_screenshots_of_threads_posts(content_object: dict, screenshot_num: int) -> None:
    """
    Downloads screenshots of Threads posts via Playwright.

    Args:
        content_object: Standard content dict from platforms/threads/fetcher.py
        screenshot_num: Number of reply screenshots to capture
    """
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])
    storymode: Final[bool] = settings.config["settings"]["storymode"]

    print_step("Downloading screenshots of Threads posts...")

    thread_id = re.sub(r"[^\w\s-]", "", content_object["thread_id"])
    Path(f"assets/temp/{thread_id}/png").mkdir(parents=True, exist_ok=True)

    # Theme colors
    theme = settings.config["settings"]["theme"]
    if theme == "dark":
        bgcolor = (33, 33, 36, 255)
        txtcolor = (240, 240, 240)
    else:
        bgcolor = (255, 255, 255, 255)
        txtcolor = (0, 0, 0)

    # Device scale factor (higher resolution screenshots)
    dsf = (W // 600) + 1

    with sync_playwright() as p:
        print_substep("Launching headless browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="en-US",
            color_scheme="dark" if theme == "dark" else "light",
            viewport=ViewportSize(width=W, height=H),
            device_scale_factor=dsf,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # Try to load saved cookies; if not found or invalid, do a fresh login
        cookie_path = Path(THREADS_COOKIE_FILE)
        if cookie_path.exists():
            try:
                with open(cookie_path, encoding="utf-8") as f:
                    saved_cookies = json.load(f)
                context.add_cookies(saved_cookies)
                print_substep("Loaded saved Threads session cookies.")
            except (json.JSONDecodeError, IOError):
                print_substep("Saved cookies corrupted. Logging in fresh...")
                page = context.new_page()
                _login_to_threads(page, context)
                page.close()
        else:
            print_substep("No saved cookies found. Logging in...")
            page = context.new_page()
            _login_to_threads(page, context)
            page.close()

        # Screenshot the main post
        page = context.new_page()
        page.goto(content_object["thread_url"], timeout=0)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        postcontentpath = f"assets/temp/{thread_id}/png/title.png"
        try:
            # On Threads.net post permalink pages, the main post is the first article element
            post_locator = page.locator("article").first
            if not post_locator.is_visible():
                raise RuntimeError(
                    "Main post article not found on page. "
                    "Check if you're logged in correctly or if the post is deleted."
                )

            if settings.config["settings"].get("zoom", 1) != 1:
                zoom = settings.config["settings"]["zoom"]
                page.evaluate(f"document.body.style.zoom={zoom}")
                location = post_locator.bounding_box()
                if location:
                    for k in location:
                        location[k] = float("{:.2f}".format(location[k] * zoom))
                    page.screenshot(clip=location, path=postcontentpath)
                else:
                    post_locator.screenshot(path=postcontentpath)
            else:
                post_locator.screenshot(path=postcontentpath)

            print_substep("Main post screenshot captured.", style="bold green")
        except Exception as e:
            print_substep(f"Failed to screenshot main post: {e}", style="red")
            raise

        # Screenshots of replies
        if not storymode:
            for idx in range(min(screenshot_num, len(content_object["comments"]))):
                comment = content_object["comments"][idx]
                try:
                    page.goto(comment["comment_url"], timeout=0)
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(2000)

                    # Each reply permalink page shows that reply as the first article
                    reply_locator = page.locator("article").first
                    if not reply_locator.is_visible():
                        print_substep(f"Reply {idx} article not found. Skipping...", style="yellow")
                        continue

                    if settings.config["settings"].get("zoom", 1) != 1:
                        zoom = settings.config["settings"]["zoom"]
                        page.evaluate(f"document.body.style.zoom={zoom}")
                        location = reply_locator.bounding_box()
                        if location:
                            for k in location:
                                location[k] = float("{:.2f}".format(location[k] * zoom))
                            page.screenshot(
                                clip=location,
                                path=f"assets/temp/{thread_id}/png/comment_{idx}.png",
                            )
                        else:
                            reply_locator.screenshot(
                                path=f"assets/temp/{thread_id}/png/comment_{idx}.png"
                            )
                    else:
                        reply_locator.screenshot(
                            path=f"assets/temp/{thread_id}/png/comment_{idx}.png"
                        )

                except Exception as e:
                    print_substep(f"Error capturing reply {idx}: {e}. Skipping...", style="yellow")
                    # Don't crash; just skip this reply
                    continue

            print_substep(f"Reply screenshots captured ({min(screenshot_num, len(content_object['comments']))} total).", style="bold green")

        browser.close()

    print_substep("Threads screenshots downloaded successfully.", style="bold green")
