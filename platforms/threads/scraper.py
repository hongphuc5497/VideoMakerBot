"""Web scraping-based trending post discovery for Threads.net.

Bypasses the Meta Graph API (which only accesses your own posts) by using Playwright
to scrape threads.net directly — the "For You" feed, post pages, and replies.
Returns the standard content_object dict consumed by the rest of the pipeline.
"""

import re
from typing import Optional

from playwright.sync_api import BrowserContext, Locator, sync_playwright

from platforms.threads.auth import ensure_authenticated_context
from utils import settings
from utils.console import emit_scraper_event, print_step, print_substep
from utils.voice import sanitize_text
from utils.videos import check_done_by_id

FEED_URL = "https://www.threads.net"
SCROLL_DELAY_MS = 2000
MAX_FEED_SCROLLS = 36
POST_LINK_SELECTOR = 'a[href*="/post/"]'
CARD_XPATH = 'xpath=ancestor::div[contains(@class, "x1a2a7pz")][1]'


def _post_id_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def _to_absolute_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return "https://www.threads.net" + href


def _parse_abbreviated_number(s: str) -> int:
    """Parse abbreviated numbers like '1K', '2.5M' into integers."""
    s = s.strip().upper().replace(",", "")
    if not s:
        return 0
    multipliers = {"K": 1_000, "M": 1_000_000}
    if s[-1] in multipliers:
        try:
            return int(float(s[:-1]) * multipliers[s[-1]])
        except ValueError:
            return 0
    try:
        return int(s)
    except ValueError:
        return 0


def _parse_card_text(text: str) -> dict:
    """Parse a Threads card's raw text into structured data.

    Threads card format:
      line 0:   username
      line 1:   timestamp (e.g. "14h", "1d")
      lines 2..N: post body text
      last 1-4 lines: engagement metrics (likes, replies, reposts, quotes)

    Returns dict with keys: username, timestamp, body, likes, replies, reposts
    """
    if not text:
        return {"username": "", "timestamp": "", "body": "", "likes": 0, "replies": 0, "reposts": 0}

    lines = text.strip().split("\n")
    if len(lines) < 3:
        return {"username": "", "timestamp": "", "body": text, "likes": 0, "replies": 0, "reposts": 0}

    username = lines[0].strip()
    timestamp = lines[1].strip()

    # Find where engagement metrics start (trailing numeric/abbreviated lines)
    metric_start = len(lines)
    for i in range(len(lines) - 1, 1, -1):
        line = lines[i].strip()
        if re.match(r'^[\d,.]+[KkMm]?$', line):
            metric_start = i
        else:
            break

    # Body is everything between timestamp and metrics
    body_lines = lines[2:metric_start]
    body = "\n".join(body_lines).strip()

    # Parse engagement metrics from the end
    metrics = lines[metric_start:]
    likes = 0
    replies_count = 0
    reposts = 0

    if len(metrics) >= 1:
        likes = _parse_abbreviated_number(metrics[0])
    if len(metrics) >= 2:
        replies_count = _parse_abbreviated_number(metrics[1])
    if len(metrics) >= 3:
        reposts = _parse_abbreviated_number(metrics[2])

    return {
        "username": username,
        "timestamp": timestamp,
        "body": body,
        "likes": likes,
        "replies": replies_count,
        "reposts": reposts,
    }


def _extract_text_from_card(link: Locator) -> str:
    """Walk up from a post link to the card container and extract its raw text."""
    try:
        card = link.locator(CARD_XPATH)
        if card.count():
            return card.first.inner_text(timeout=3000).strip()
    except Exception:
        pass
    return ""


# --- Feed scraping ---


def _scrape_feed_posts(context: BrowserContext, max_scrolls: int = MAX_FEED_SCROLLS) -> list[dict]:
    """Navigate to threads.net feed, scroll, extract post metadata with engagement metrics."""
    print_step("Scraping Threads trending feed...")
    emit_scraper_event("browser_launch", {"message": "Scraping Threads trending feed"})
    page = context.new_page()
    posts: list[dict] = []
    seen_ids: set[str] = set()

    try:
        page.goto(FEED_URL, timeout=0)
        page.wait_for_timeout(4000)

        last_height = 0

        for i in range(max_scrolls):
            links = page.locator(POST_LINK_SELECTOR).all()
            new_found = 0

            for link in links:
                href = link.get_attribute("href")
                if not href:
                    continue
                post_id = _post_id_from_url(href)
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                raw_text = _extract_text_from_card(link)
                parsed = _parse_card_text(raw_text)

                posts.append({
                    "url": _to_absolute_url(href),
                    "text": raw_text,
                    "body": parsed["body"],
                    "username": parsed["username"],
                    "timestamp": parsed["timestamp"],
                    "likes": parsed["likes"],
                    "replies_shown": parsed["replies"],
                    "reposts": parsed["reposts"],
                    "post_id": post_id,
                })
                new_found += 1

                emit_scraper_event("post_discovered", {
                    "username": parsed["username"],
                    "body": parsed["body"][:100],
                    "likes": parsed["likes"],
                    "replies": parsed["replies"],
                    "reposts": parsed["reposts"],
                    "post_id": post_id,
                })

            if new_found > 0:
                top = posts[-1]
                print_substep(
                    f"Scroll {i + 1}: +{new_found} posts | top: "
                    f"♥{top['likes']:,} 💬{top['replies_shown']} 🔁{top['reposts']} "
                    f"'{top['body'][:50]}...'",
                    style="dim",
                )

            emit_scraper_event("feed_scroll", {
                "scroll": i + 1,
                "new_posts": new_found,
                "total_posts": len(posts),
                "max_scrolls": max_scrolls,
            })

            if new_found == 0 and i > 5:
                break

            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(SCROLL_DELAY_MS)

            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    finally:
        page.close()

    print_substep(f"Scraped {len(posts)} posts from feed.", style="bold green")
    return posts


def _scrape_search_page(context: BrowserContext, query: str, max_scrolls: int = 5) -> list[dict]:
    """Search Threads for a query and scrape the results.

    Uses the same card extraction as the main feed.
    """
    print_step(f"Scraping Threads search: '{query}'...")
    emit_scraper_event("search_query", {"query": query, "posts_found": 0})
    page = context.new_page()
    posts: list[dict] = []
    seen_ids: set[str] = set()
    search_url = f"https://www.threads.net/search?q={query}&serp_type=tags"

    try:
        page.goto(search_url, timeout=0)
        page.wait_for_timeout(4000)

        for i in range(max_scrolls):
            links = page.locator(POST_LINK_SELECTOR).all()
            new_found = 0

            for link in links:
                href = link.get_attribute("href")
                if not href:
                    continue
                post_id = _post_id_from_url(href)
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                raw_text = _extract_text_from_card(link)
                parsed = _parse_card_text(raw_text)

                posts.append({
                    "url": _to_absolute_url(href),
                    "text": raw_text,
                    "body": parsed["body"],
                    "username": parsed["username"],
                    "timestamp": parsed["timestamp"],
                    "likes": parsed["likes"],
                    "replies_shown": parsed["replies"],
                    "reposts": parsed["reposts"],
                    "post_id": post_id,
                })
                new_found += 1

            if new_found == 0:
                break

            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(SCROLL_DELAY_MS)

    finally:
        page.close()

    print_substep(f"Search '{query}': {len(posts)} posts.", style="dim")
    emit_scraper_event("search_query", {"query": query, "posts_found": len(posts)})
    return posts


# --- Candidate filtering ---


def _parse_timestamp_to_hours(ts: str) -> float | None:
    """Convert a Threads timestamp like '14h', '1d', '3d' to hours.

    Returns None if the format is unrecognized.
    """
    if not ts:
        return None
    ts = ts.strip().lower()
    if ts.endswith("h"):
        try:
            return float(ts[:-1])
        except ValueError:
            return None
    elif ts.endswith("d"):
        try:
            return float(ts[:-1]) * 24
        except ValueError:
            return None
    elif ts.endswith("w"):
        try:
            return float(ts[:-1]) * 24 * 7
        except ValueError:
            return None
    elif ts.endswith("m") and not ts.endswith("min"):
        try:
            return float(ts[:-1]) * 24 * 30
        except ValueError:
            return None
    return None


def _age_from_config() -> float | None:
    """Parse max_post_age config value into hours. Returns None if disabled."""
    raw = settings.config["threads"]["thread"].get("max_post_age", "")
    if not raw:
        return None
    return _parse_timestamp_to_hours(raw)


def _contains_blocked(text: str, blocked_raw: str) -> bool:
    if not blocked_raw:
        return False
    blocked = [w.strip().lower() for w in blocked_raw.split(",") if w.strip()]
    text_lower = text.lower()
    return any(word in text_lower for word in blocked)


def _filter_candidates(posts: list[dict]) -> list[dict]:
    """Filter feed posts by engagement, blocked words, and duplicates.

    Sorts by total engagement (likes + replies) descending so the most
    viral posts are tried first.
    """
    t_config = settings.config["threads"]["thread"]
    blocked_raw = t_config.get("blocked_words", "")
    min_engagement = int(t_config.get("min_engagement", 0))

    max_age_hours = _age_from_config()

    candidates = []
    for post in posts:
        if check_done_by_id(post["post_id"]):
            continue
        if _contains_blocked(post["body"], blocked_raw):
            continue
        if not post["body"] or len(post["body"].strip()) < 10:
            continue
        # Age filter
        if max_age_hours is not None:
            post_hours = _parse_timestamp_to_hours(post.get("timestamp", ""))
            if post_hours is not None and post_hours > max_age_hours:
                continue
        total_engagement = post.get("likes", 0) + post.get("reposts", 0)
        if total_engagement < min_engagement:
            continue
        post["_total_engagement"] = total_engagement
        candidates.append(post)

    # Sort by engagement descending — most viral first
    candidates.sort(key=lambda p: p.get("_total_engagement", 0), reverse=True)

    emit_scraper_event("filter_results", {
        "before": len(posts),
        "after": len(candidates),
        "min_engagement": min_engagement,
        "max_age_hours": max_age_hours,
    })

    age_str = f", max age ≤{max_age_hours}h" if max_age_hours else ""
    if min_engagement > 0:
        print_substep(
            f"Filtered {len(posts)} posts -> {len(candidates)} viral candidates "
            f"(min ♥+🔁 ≥ {min_engagement:,}{age_str})",
            style="dim",
        )
    else:
        print_substep(
            f"Filtered {len(posts)} posts -> {len(candidates)} candidates"
            f"{' (max age ≤' + str(max_age_hours) + 'h)' if max_age_hours else ''}",
            style="dim",
        )
    return candidates


# --- Reply scraping on post pages ---


def _scrape_post_replies(context: BrowserContext, post_url: str, max_replies: int = 100) -> list[dict]:
    """Navigate to a post page, scroll to load replies, extract reply data.

    Uses _parse_card_text to separate reply body from metadata (username, timestamp, etc.).
    """
    page = context.new_page()
    replies: list[dict] = []
    seen_ids: set[str] = set()
    main_post_id = _post_id_from_url(post_url)

    try:
        page.goto(post_url, timeout=0)
        page.wait_for_timeout(4000)

        stable_count = 0
        last_count = 0

        for _ in range(15):
            links = page.locator(POST_LINK_SELECTOR).all()

            for link in links:
                href = link.get_attribute("href")
                if not href:
                    continue
                reply_id = _post_id_from_url(href)
                if reply_id == main_post_id:
                    continue
                if reply_id in seen_ids:
                    continue
                seen_ids.add(reply_id)

                raw_text = _extract_text_from_card(link)
                if not raw_text:
                    continue

                parsed = _parse_card_text(raw_text)
                cleaned_body = parsed["body"]

                replies.append({
                    "comment_body": cleaned_body,
                    "comment_url": _to_absolute_url(href),
                    "comment_id": reply_id,
                })

                if len(replies) >= max_replies:
                    break

            if len(replies) >= max_replies:
                break

            if len(replies) == last_count:
                stable_count += 1
                if stable_count >= 3:
                    break
            else:
                stable_count = 0
            last_count = len(replies)

            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)

    finally:
        page.close()

    return replies


def _scrape_main_post_text(context: BrowserContext, post_url: str) -> str:
    """Extract and clean the main post text from a post page."""
    page = context.new_page()
    try:
        page.goto(post_url, timeout=0)
        page.wait_for_timeout(3000)

        links = page.locator(POST_LINK_SELECTOR).all()
        for link in links:
            href = link.get_attribute("href")
            if href and _post_id_from_url(href) == _post_id_from_url(post_url):
                raw = _extract_text_from_card(link)
                if raw:
                    parsed = _parse_card_text(raw)
                    return parsed["body"] or raw
        return ""
    finally:
        page.close()


# --- Content object builder ---


def _build_content_object(post: dict, replies: list[dict]) -> dict:
    """Build the standard content_object from scraped post + replies.

    Uses cleaned body text for title and comment bodies.
    """
    t_config = settings.config["threads"]["thread"]
    max_len = int(t_config["max_reply_length"])
    min_len = int(t_config["min_reply_length"])
    blocked_raw = t_config.get("blocked_words", "")

    storymode = settings.config["settings"].get("storymode", False)

    # Use cleaned body text for the title, fall back to raw text
    title = post.get("body") or post.get("text") or ""

    content: dict = {
        "thread_id": post["post_id"],
        "thread_title": title[:280],
        "thread_url": post["url"],
        "is_nsfw": False,
        "thread_category": "threads",
        "comments": [],
    }

    if storymode:
        content["thread_post"] = title
        print_substep("Storymode: using post text as thread_post.", style="dim")
        return content

    for reply in replies:
        body = reply.get("comment_body", "").strip()
        if not body:
            continue
        if _contains_blocked(body, blocked_raw):
            continue
        if not (min_len <= len(body) <= max_len):
            continue
        sanitised = sanitize_text(body)
        if not sanitised:
            continue

        content["comments"].append({
            "comment_body": body,
            "comment_url": reply["comment_url"],
            "comment_id": reply["comment_id"],
        })

    return content


# --- Main entry point ---


def get_trending_threads_content(POST_ID: Optional[str] = None) -> dict:
    """Discover trending Threads posts via web scraping and return a content_object."""
    print_step("Discovering trending Threads content via web scraping...")

    min_replies = int(settings.config["threads"]["thread"]["min_replies"])
    min_engagement = int(settings.config["threads"]["thread"].get("min_engagement", 0))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = ensure_authenticated_context(browser)

            if POST_ID:
                post_url = f"https://www.threads.net/t/{POST_ID}"
                post = {"url": post_url, "post_id": POST_ID, "text": "", "body": ""}
                replies = _scrape_post_replies(context, post_url)
                content = _build_content_object(post, replies)
                if content["comments"] or content.get("thread_post"):
                    return content
                raise RuntimeError(
                    f"No replies found for post {POST_ID}. "
                    f"Minimum required: {min_replies}."
                )

            # Scrape from multiple sources: main feed + trending search queries
            posts = _scrape_feed_posts(context)
            # Also search for popular topics to find high-engagement content
            trending_queries = settings.config["threads"]["thread"].get(
                "search_queries", "news,politics,trending"
            )
            for query in trending_queries.split(","):
                query = query.strip()
                if query:
                    try:
                        search_posts = _scrape_search_page(context, query)
                        # Merge avoiding duplicates
                        existing_ids = {p["post_id"] for p in posts}
                        for sp in search_posts:
                            if sp["post_id"] not in existing_ids:
                                posts.append(sp)
                    except Exception:
                        pass

            if not posts:
                raise RuntimeError("No posts found in feed. Try again later.")

            candidates = _filter_candidates(posts)
            if not candidates:
                raise RuntimeError(
                    f"No eligible posts in feed after filtering. "
                    f"Try lowering min_engagement (currently {min_engagement:,}) "
                    f"or min_replies (currently {min_replies})."
                )

            for i, candidate in enumerate(candidates):
                eng = candidate.get("_total_engagement", 0)
                print_substep(
                    f"Trying #{i + 1}: ♥{candidate['likes']:,} "
                    f"💬{candidate['replies_shown']} "
                    f"'{candidate['body'][:60]}...'",
                    style="dim",
                )
                emit_scraper_event("visiting_post", {
                    "post_id": candidate["post_id"],
                    "url": candidate["url"],
                    "engagement": eng,
                    "likes": candidate.get("likes", 0),
                    "body": candidate.get("body", "")[:60],
                    "attempt": i + 1,
                })
                try:
                    replies = _scrape_post_replies(context, candidate["url"])
                    emit_scraper_event("replies_found", {
                        "post_id": candidate["post_id"],
                        "count": len(replies),
                        "min_required": min_replies,
                    })
                    if len(replies) >= min_replies:
                        if not candidate.get("body") or len(candidate.get("body", "")) < 50:
                            full_text = _scrape_main_post_text(context, candidate["url"])
                            if full_text:
                                candidate["body"] = full_text
                        content = _build_content_object(candidate, replies)
                        title_preview = content["thread_title"][:60]
                        print_substep(
                            f"Selected: '{title_preview}...' "
                            f"♥{candidate['likes']:,} 💬{len(content['comments'])} replies",
                            style="bold green",
                        )
                        emit_scraper_event("post_selected", {
                            "title": content["thread_title"][:80],
                            "post_id": candidate["post_id"],
                            "likes": candidate["likes"],
                            "replies_count": len(content["comments"]),
                            "url": candidate["url"],
                        })
                        return content
                    print_substep(
                        f"  Only {len(replies)} replies (need {min_replies}). Trying next...",
                        style="yellow",
                    )
                except Exception as e:
                    print_substep(f"  Failed: {e}. Trying next...", style="yellow")
                    continue

            raise RuntimeError(
                f"No eligible posts with {min_replies}+ replies found "
                f"after trying {len(candidates)} candidates."
            )

        finally:
            browser.close()
