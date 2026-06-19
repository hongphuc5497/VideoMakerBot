import requests

from utils.console import print_step

# Set to the correct GitHub "owner/repo" for this fork, or leave empty to skip check.
_UPSTREAM_REPO = ""


def checkversion(__VERSION__: str):
    if not _UPSTREAM_REPO:
        return
    try:
        response = requests.get(
            f"https://api.github.com/repos/{_UPSTREAM_REPO}/releases/latest",
            timeout=10,
        )
        response.raise_for_status()
        latestversion = response.json()["tag_name"]
    except (requests.RequestException, KeyError, ValueError):
        return  # Network or API error — skip version check silently

    if __VERSION__ == latestversion:
        print_step(f"You are using the newest version ({__VERSION__}) of the bot")
    elif __VERSION__ < latestversion:
        print_step(
            f"You are using an older version ({__VERSION__}) of the bot. "
            f"Download the newest version ({latestversion}) from "
            f"https://github.com/{_UPSTREAM_REPO}/releases/latest"
        )
    else:
        print_step(
            f"Welcome to the test version ({__VERSION__}) of the bot. "
            f"Thanks for testing and feel free to report any bugs you find."
        )
