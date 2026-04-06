"""Fetches content from Meta Threads via the Graph API."""

import requests
from typing import Optional

from utils import settings
from utils.console import print_step, print_substep
from utils.voice import sanitize_text
from utils.videos import check_done_by_id


GRAPH_API_BASE = "https://graph.threads.net/v1.0"


def _get_headers() -> dict:
    """Returns HTTP headers with Bearer token for Graph API requests."""
    token = settings.config["threads"]["creds"]["access_token"]
    if not token:
        raise RuntimeError(
            "Threads API: access_token is required. "
            "Set it in config.toml under [threads.creds]."
        )
    return {"Authorization": f"Bearer {token}"}


def _api_get(url: str, params: dict = None) -> dict:
    """Makes a GET request to Threads Graph API with error handling."""
    try:
        resp = requests.get(url, headers=_get_headers(), params=params or {}, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            raise RuntimeError(
                "Threads API: Invalid or expired access_token. "
                "Tokens are valid for 60 days. Refresh at: "
                "https://developers.facebook.com/tools/explorer/"
            ) from e
        if e.response.status_code == 400:
            error_msg = e.response.json().get("error", {}).get("message", str(e))
            raise RuntimeError(f"Threads API: Bad request — {error_msg}") from e
        raise RuntimeError(f"Threads API: HTTP {e.response.status_code}") from e
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError("Threads API: Cannot connect. Check internet connection.") from e
    except requests.exceptions.Timeout as e:
        raise RuntimeError("Threads API: Request timed out.") from e


def _fetch_post(post_id: str) -> dict:
    """Fetches a single Threads post by ID."""
    url = f"{GRAPH_API_BASE}/{post_id}"
    params = {"fields": "id,text,timestamp,permalink,is_quote_post,media_type"}
    return _api_get(url, params)


def _fetch_replies(post_id: str, limit: int = 50) -> list:
    """Fetches all replies to a Threads post, handling pagination."""
    url = f"{GRAPH_API_BASE}/{post_id}/replies"
    params = {
        "fields": "id,text,timestamp,username,permalink",
        "limit": limit,
    }
    results = []

    while url:
        data = _api_get(url, params)
        results.extend(data.get("data", []))
        # Handle pagination — next URL is provided in paging.next
        url = data.get("paging", {}).get("next")
        params = {}  # Next URL already includes all params

    return results


def _pick_best_post() -> tuple:
    """
    Fetches recent posts from the user and returns the first one
    with enough replies that hasn't been processed yet.

    Returns:
        tuple: (post_dict, replies_list)

    Raises:
        RuntimeError: If no eligible posts are found.
    """
    user_id = settings.config["threads"]["creds"]["user_id"]
    if not user_id:
        raise RuntimeError(
            "Threads API: user_id is required. "
            "Set it in config.toml under [threads.creds]."
        )

    url = f"{GRAPH_API_BASE}/{user_id}/threads"
    params = {"fields": "id,text,timestamp,permalink,media_type", "limit": 25}

    data = _api_get(url, params)
    posts = data.get("data", [])

    min_replies = settings.config["threads"]["thread"]["min_replies"]

    for post in posts:
        if check_done_by_id(post["id"]):
            continue

        replies = _fetch_replies(post["id"])
        if len(replies) >= min_replies:
            return post, replies

    raise RuntimeError(
        f"No eligible Threads posts found. "
        f"Ensure you have posts with at least {min_replies} replies."
    )


def get_threads_content(POST_ID: str = None) -> dict:
    """
    Fetches Threads content (post + replies) and returns it in the standard content_object format.

    Args:
        POST_ID (str, optional): Specific post ID to fetch. If None, auto-selects.

    Returns:
        dict: Standard content_object matching the pipeline contract.

    Raises:
        RuntimeError: On API errors or if no eligible content found.
    """
    print_step("Fetching Threads content...")

    # Determine which post to fetch
    if POST_ID:
        post = _fetch_post(POST_ID)
        replies = _fetch_replies(POST_ID)
    elif settings.config["threads"]["thread"].get("post_id"):
        post_id = settings.config["threads"]["thread"]["post_id"]
        post = _fetch_post(post_id)
        replies = _fetch_replies(post_id)
    else:
        post, replies = _pick_best_post()

    # Load content filters from config
    max_len = settings.config["threads"]["thread"]["max_reply_length"]
    min_len = settings.config["threads"]["thread"]["min_reply_length"]
    blocked_raw = settings.config["threads"]["thread"].get("blocked_words", "")
    blocked = [w.strip().lower() for w in blocked_raw.split(",") if w.strip()]

    # Build content object in standard format
    content = {
        "thread_id": post["id"],
        "thread_title": (post.get("text") or "")[:280],  # Threads has no separate title
        "thread_url": post["permalink"],
        "is_nsfw": False,  # Threads API doesn't provide NSFW flag
        "thread_category": "threads",  # Generic field for output folder naming
        "comments": [],
    }

    # Filter and add replies
    for reply in replies:
        body = reply.get("text", "").strip()
        if not body:
            continue

        # Check blocked words
        if any(w in body.lower() for w in blocked):
            continue

        # Check length constraints
        if not (min_len <= len(body) <= max_len):
            continue

        # Sanitize text
        sanitised = sanitize_text(body)
        if not sanitised:
            continue

        content["comments"].append({
            "comment_body": body,
            "comment_url": reply["permalink"],
            "comment_id": reply["id"],
        })

    # Log summary
    title_preview = content["thread_title"][:60]
    print_substep(
        f"Fetched Threads post '{title_preview}...' "
        f"with {len(content['comments'])} replies.",
        style="bold green",
    )

    return content
