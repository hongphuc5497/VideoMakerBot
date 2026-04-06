"""Platform abstraction layer for content source selection."""

from utils import settings


def get_content_object(POST_ID=None) -> dict:
    """
    Returns a populated content_object dict for the configured platform.
    Dispatches to the appropriate platform fetcher based on settings.config["settings"]["platform"].

    Args:
        POST_ID (str, optional): Specific post ID to fetch. If None, auto-selects a post.

    Returns:
        dict: Standard content_object with keys:
            - thread_id, thread_title, thread_url, is_nsfw, thread_category, comments
            - (or thread_post if storymode is enabled)

    Raises:
        ValueError: If platform is unknown or invalid.
    """
    platform = settings.config["settings"].get("platform", "reddit").lower()

    if platform == "reddit":
        from reddit.subreddit import get_subreddit_threads
        return get_subreddit_threads(POST_ID)

    elif platform == "threads":
        from platforms.threads.fetcher import get_threads_content
        return get_threads_content(POST_ID)

    else:
        raise ValueError(
            f"Unknown platform: '{platform}'. Valid options: reddit, threads"
        )


def get_screenshot_fn(platform: str = None):
    """
    Returns the appropriate screenshot function for the given platform.

    Args:
        platform (str, optional): Platform name. If None, uses the configured platform.

    Returns:
        callable: Screenshot function that takes (content_object, screenshot_num).

    Raises:
        ValueError: If platform is unknown or invalid.
    """
    if platform is None:
        platform = settings.config["settings"].get("platform", "reddit").lower()

    if platform == "reddit":
        from video_creation.screenshot_downloader import get_screenshots_of_reddit_posts
        return get_screenshots_of_reddit_posts

    elif platform == "threads":
        from platforms.threads.screenshot import get_screenshots_of_threads_posts
        return get_screenshots_of_threads_posts

    else:
        raise ValueError(
            f"Unknown platform: '{platform}'. Valid options: reddit, threads"
        )
