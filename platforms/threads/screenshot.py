"""Captures screenshots of Threads posts via Playwright."""

import re
from pathlib import Path
from typing import Final

from playwright.sync_api import ViewportSize, sync_playwright

from platforms.threads.auth import ensure_authenticated_context
from utils import settings
from utils.console import print_step, print_substep


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
        context = ensure_authenticated_context(
            browser,
            color_scheme="dark" if theme == "dark" else "light",
            viewport=ViewportSize(width=W, height=H),
            device_scale_factor=dsf,
        )

        # Screenshot the main post
        page = context.new_page()
        page.goto(content_object["thread_url"], timeout=0)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        postcontentpath = f"assets/temp/{thread_id}/png/title.png"
        try:
            # Threads.net uses div-based cards, not <article> elements.
            # Find the first post link and screenshot its parent card.
            post_link = page.locator('a[href*="/post/"]').first
            if post_link.count() and post_link.is_visible():
                # Screenshot the card container, or fall back to the link's parent
                card = post_link.locator('xpath=ancestor::div[contains(@class, "x1a2a7pz")][1]')
                if card.count():
                    post_locator = card.first
                else:
                    post_locator = post_link
            else:
                # Fallback: try article (older Threads layout) or full page
                post_locator = page.locator("article").first
                if not post_locator.count() or not post_locator.is_visible():
                    post_locator = page.locator("body")

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

                    # Threads.net uses div-based cards for replies too.
                    # Target the specific reply by its comment_id in the URL.
                    # Using .first would pick the main post (appears first in DOM).
                    reply_id = comment["comment_id"]
                    reply_link = page.locator(f'a[href*="/{reply_id}"]').first
                    if reply_link.count() and reply_link.is_visible():
                        card = reply_link.locator('xpath=ancestor::div[contains(@class, "x1a2a7pz")][1]')
                        reply_locator = card.first if card.count() else reply_link
                    else:
                        reply_locator = page.locator("article").first
                    if not reply_locator.count() or not reply_locator.is_visible():
                        print_substep(f"Reply {idx} not found. Skipping...", style="yellow")
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
