#!/usr/bin/env python
import math
import subprocess
import sys
from os import name
from pathlib import Path
from typing import Dict, NoReturn, Union

from platforms import get_content_object, get_screenshot_fn
from utils import settings
from utils.cleanup import cleanup
from utils.console import print_markdown, print_step, print_substep
from utils.ffmpeg_install import ffmpeg_install
from utils.id import extract_id
from utils.version import checkversion
from video_creation.background import (
    chop_background,
    download_background_audio,
    download_background_video,
    get_background_config,
)
from video_creation.final_video import make_final_video, name_normalize
from video_creation.voices import save_text_to_mp3
from video_creation.youtube_uploader import upload_to_youtube

# Guard prawcore import — only available when Reddit is used
try:
    from prawcore import ResponseException as _PrawResponseException
except ImportError:
    _PrawResponseException = None

__VERSION__ = "3.4.0"

print(
    """
██████╗ ███████╗██████╗ ██████╗ ██╗████████╗    ██╗   ██╗██╗██████╗ ███████╗ ██████╗     ███╗   ███╗ █████╗ ██╗  ██╗███████╗██████╗
██╔══██╗██╔════╝██╔══██╗██╔══██╗██║╚══██╔══╝    ██║   ██║██║██╔══██╗██╔════╝██╔═══██╗    ████╗ ████║██╔══██╗██║ ██╔╝██╔════╝██╔══██╗
██████╔╝█████╗  ██║  ██║██║  ██║██║   ██║       ██║   ██║██║██║  ██║█████╗  ██║   ██║    ██╔████╔██║███████║█████╔╝ █████╗  ██████╔╝
██╔══██╗██╔══╝  ██║  ██║██║  ██║██║   ██║       ╚██╗ ██╔╝██║██║  ██║██╔══╝  ██║   ██║    ██║╚██╔╝██║██╔══██║██╔═██╗ ██╔══╝  ██╔══██╗
██║  ██║███████╗██████╔╝██████╔╝██║   ██║        ╚████╔╝ ██║██████╔╝███████╗╚██████╔╝    ██║ ╚═╝ ██║██║  ██║██║  ██╗███████╗██║  ██║
╚═╝  ╚═╝╚══════╝╚═════╝ ╚═════╝ ╚═╝   ╚═╝         ╚═══╝  ╚═╝╚═════╝ ╚══════╝ ╚═════╝     ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
"""
)
print_markdown(
    "### Thanks for using this tool! Feel free to contribute to this project on GitHub! If you have any questions, feel free to join my Discord server or submit a GitHub issue. You can find solutions to many common problems in the documentation: https://reddit-video-maker-bot.netlify.app/"
)
checkversion(__VERSION__)

reddit_id: str
reddit_object: Dict[str, Union[str, list]]


def _get_platform_post_id(config: dict, platform: str) -> str:
    """Returns the post_id string from config for the active platform."""
    if platform == "reddit":
        return config.get("reddit", {}).get("thread", {}).get("post_id", "")
    elif platform == "threads":
        return config.get("threads", {}).get("thread", {}).get("post_id", "")
    return ""


def main(POST_ID=None) -> None:
    global reddit_id, reddit_object
    reddit_object = get_content_object(POST_ID)
    reddit_id = extract_id(reddit_object)
    print_substep(f"Thread ID is {reddit_id}", style="bold blue")
    length, number_of_comments = save_text_to_mp3(reddit_object)
    length = math.ceil(length)
    screenshot_fn = get_screenshot_fn()
    screenshot_fn(reddit_object, number_of_comments)
    bg_config = {
        "video": get_background_config("video"),
        "audio": get_background_config("audio"),
    }
    download_background_video(bg_config["video"])
    download_background_audio(bg_config["audio"])
    chop_background(bg_config, length, reddit_object)
    make_final_video(number_of_comments, length, reddit_object, bg_config)

    # -- YouTube upload (if enabled in config) ---------------------------
    youtube_config = settings.config.get("youtube", {})
    if youtube_config.get("enabled", False):
        # Compute the video path using the same logic as final_video.py
        title_raw = reddit_object.get("thread_title", "video")
        filename = f"{name_normalize(title_raw)[:251]}"
        platform = settings.config["settings"].get("platform", "reddit")
        if platform == "reddit":
            subreddit = (
                settings.config.get("reddit", {})
                .get("thread", {})
                .get("subreddit", "unknown")
            )
        else:
            subreddit = reddit_object.get("thread_category", platform)
        video_path = f"results/{subreddit}/{filename}.mp4"

        youtube_url = upload_to_youtube(
            video_path, title_raw, settings.config
        )
        if youtube_url:
            print_substep(f"YouTube URL: {youtube_url}", "bold green")
        else:
            print_substep("YouTube upload skipped or failed.", "yellow")
    # ---------------------------------------------------------------------


def run_many(times) -> None:
    for x in range(1, times + 1):
        print_step(
            f'on the {x}{("th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th")[x % 10]} iteration of {times}'
        )
        main()
        subprocess.run(["cls" if name == "nt" else "clear"], shell=(name == "nt"))


def shutdown() -> NoReturn:
    if "reddit_id" in globals():
        print_markdown("## Clearing temp files")
        cleanup(reddit_id)

    print("Exiting...")
    sys.exit()


if __name__ == "__main__":
    if sys.version_info.major != 3 or sys.version_info.minor < 10:
        print(
            "Hey! Congratulations, you've made it so far (which is pretty rare with no Python 3.10). Unfortunately, this program requires Python 3.10 or later. Please install Python 3.10+ and try again."
        )
        sys.exit()
    ffmpeg_install()
    directory = Path().absolute()
    config = settings.check_toml(
        f"{directory}/utils/.config.template.toml", f"{directory}/config.toml"
    )
    config is False and sys.exit()

    if (
        not settings.config["settings"]["tts"]["tiktok_sessionid"]
        or settings.config["settings"]["tts"]["tiktok_sessionid"] == ""
    ) and config["settings"]["tts"]["voice_choice"] == "tiktok":
        print_substep(
            "TikTok voice requires a sessionid! "
            "Falling back to pyttsx3 (offline TTS, no API key needed). "
            "Set a valid tiktok_sessionid in your config.toml to use TikTok voices.",
            "bold yellow",
        )
        config["settings"]["tts"]["voice_choice"] = "pyttsx"
    try:
        platform = config["settings"].get("platform", "reddit")
        post_id_str = _get_platform_post_id(config, platform)

        if post_id_str:
            for index, post_id in enumerate(post_id_str.split("+")):
                index += 1
                num_posts = len(post_id_str.split("+"))
                print_step(
                    f'on the {index}{("st" if index % 10 == 1 else ("nd" if index % 10 == 2 else ("rd" if index % 10 == 3 else "th")))} post of {num_posts}'
                )
                main(post_id)
                subprocess.run(["cls" if name == "nt" else "clear"], shell=(name == "nt"))
        elif config["settings"]["times_to_run"]:
            run_many(config["settings"]["times_to_run"])
        else:
            main()
    except KeyboardInterrupt:
        shutdown()
    except Exception as err:
        # Handle Reddit-specific credential errors if prawcore is available
        if _PrawResponseException and isinstance(err, _PrawResponseException):
            print_markdown("## Invalid Reddit credentials")
            print_markdown("Please check your credentials in the config.toml file")
            shutdown()
        # Generic error handling — redact secrets before printing
        import copy
        safe_config = copy.deepcopy(config)
        for key in ("tiktok_sessionid", "elevenlabs_api_key", "openai_api_key",
                     "client_id", "client_secret", "access_token", "password",
                     "2fa_secret"):
            safe_config.setdefault("settings", {}).setdefault("tts", {})[key] = "REDACTED"
        for section in ("reddit", "threads"):
            creds = safe_config.get(section, {}).get("creds", {})
            for cred_key in ("client_id", "client_secret", "password", "access_token", "2fa_secret"):
                if cred_key in creds:
                    creds[cred_key] = "REDACTED"
        print_step(
            f"Sorry, something went wrong with this version! Try again, and feel free to report this issue at GitHub or the Discord community.\n"
            f"Version: {__VERSION__} \n"
            f"Error: {err} \n"
            f'Config: {safe_config.get("settings", {})}'
        )
        raise
