import json
import random
import re
import subprocess
from pathlib import Path
from random import randrange
from typing import Any, Dict, Tuple

import av
import yt_dlp
from moviepy import AudioFileClip

from utils import settings
from utils.console import print_step, print_substep


def _probe_duration(path: str) -> float:
    """Get media duration in seconds using PyAV."""
    with av.open(path) as container:
        stream = container.streams[0]
        return float(stream.duration * stream.time_base)


def load_background_options():
    _background_options = {}
    # Load background videos
    with open("./utils/background_videos.json") as json_file:
        _background_options["video"] = json.load(json_file)

    # Load background audios
    with open("./utils/background_audios.json") as json_file:
        _background_options["audio"] = json.load(json_file)

    # Remove "__comment" from backgrounds
    del _background_options["video"]["__comment"]
    del _background_options["audio"]["__comment"]

    for name in list(_background_options["video"].keys()):
        pos = _background_options["video"][name][3]

        if pos != "center":
            _background_options["video"][name][3] = lambda t, p=pos: ("center", p + t)

    return _background_options


def get_start_and_end_times(video_length: int, length_of_clip: int) -> Tuple[int, int]:
    """Generates a random interval of time to be used as the background of the video.

    Args:
        video_length (int): Length of the video
        length_of_clip (int): Length of the video to be used as the background

    Returns:
        tuple[int,int]: Start and end time of the randomized interval
    """
    initialValue = 180
    # Issue #1649 - Ensures that will be a valid interval in the video
    while int(length_of_clip) <= int(video_length + initialValue):
        if initialValue == initialValue // 2:
            raise Exception("Your background is too short for this video length")
        else:
            initialValue //= 2  # Divides the initial value by 2 until reach 0
    random_time = randrange(initialValue, int(length_of_clip) - int(video_length))
    return random_time, random_time + video_length


def get_background_config(mode: str):
    """Fetch the background/s configuration"""
    try:
        choice = str(settings.config["settings"]["background"][f"background_{mode}"]).casefold()
    except AttributeError:
        print_substep("No background selected. Picking random background'")
        choice = None

    # Handle default / not supported background using default option.
    # Default : pick random from already-downloaded backgrounds if available,
    # otherwise pick from all supported backgrounds.
    if not choice or choice not in background_options[mode]:
        if mode == "video":
            available = [
                k for k, v in background_options[mode].items()
                if Path(f"assets/backgrounds/video/{v[2]}-{v[1]}").is_file()
            ]
        else:
            available = [
                k for k, v in background_options[mode].items()
                if Path(f"assets/backgrounds/audio/{v[2]}-{v[1]}").is_file()
            ]
        if available:
            choice = random.choice(available)
            print_substep(f"Picked random {mode} from downloaded: {choice}")
        else:
            choice = random.choice(list(background_options[mode].keys()))
            print_substep(f"No downloaded {mode}s found. Picked: {choice} (will download)")

    return background_options[mode][choice]


def download_background_video(background_config: Tuple[str, str, str, Any]):
    """Downloads the background/s video from YouTube."""
    Path("./assets/backgrounds/video/").mkdir(parents=True, exist_ok=True)
    # note: make sure the file name doesn't include an - in it
    uri, filename, credit, _ = background_config
    if Path(f"assets/backgrounds/video/{credit}-{filename}").is_file():
        return
    print_step(
        "We need to download the backgrounds videos. they are fairly large but it's only done once. 😎"
    )
    print_substep("Downloading the backgrounds videos... please be patient 🙏 ")
    print_substep(f"Downloading {filename} from {uri}")
    ydl_opts = {
        "format": "best[height<=1080][ext=mp4]/best[height<=1080]",
        "outtmpl": f"assets/backgrounds/video/{credit}-{filename}",
        "retries": 10,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(uri)
    print_substep("Background video downloaded successfully! 🎉", style="bold green")


def download_background_audio(background_config: Tuple[str, str, str]):
    """Downloads the background/s audio from YouTube."""
    Path("./assets/backgrounds/audio/").mkdir(parents=True, exist_ok=True)
    # note: make sure the file name doesn't include an - in it
    uri, filename, credit = background_config
    if Path(f"assets/backgrounds/audio/{credit}-{filename}").is_file():
        return
    print_step(
        "We need to download the backgrounds audio. they are fairly large but it's only done once. 😎"
    )
    print_substep("Downloading the backgrounds audio... please be patient 🙏 ")
    print_substep(f"Downloading {filename} from {uri}")
    ydl_opts = {
        "outtmpl": f"./assets/backgrounds/audio/{credit}-{filename}",
        "format": "bestaudio/best",
        "extract_audio": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([uri])

    print_substep("Background audio downloaded successfully! 🎉", style="bold green")


def chop_background(background_config: Dict[str, Tuple], video_length: int, reddit_object: dict):
    """Generates the background audio and footage to be used in the video and writes it to assets/temp/background.mp3 and assets/temp/background.mp4

    Args:
        reddit_object (Dict[str,str]) : Reddit object
        background_config (Dict[str,Tuple]]) : Current background configuration
        video_length (int): Length of the clip where the background footage is to be taken out of
    """
    thread_id = re.sub(r"[^\w\s-]", "", reddit_object["thread_id"])

    if settings.config["settings"]["background"][f"background_audio_volume"] == 0:
        print_step("Volume was set to 0. Skipping background audio creation . . .")
    else:
        print_step("Finding a spot in the backgrounds audio to chop...✂️")
        audio_choice = f"{background_config['audio'][2]}-{background_config['audio'][1]}"
        background_audio = AudioFileClip(f"assets/backgrounds/audio/{audio_choice}")
        start_time_audio, end_time_audio = get_start_and_end_times(
            video_length, background_audio.duration
        )
        background_audio = background_audio.subclipped(start_time_audio, end_time_audio)
        background_audio.write_audiofile(f"assets/temp/{thread_id}/background.mp3")

    print_step("Finding a spot in the backgrounds video to chop...✂️")
    video_choice = f"{background_config['video'][2]}-{background_config['video'][1]}"
    src = f"assets/backgrounds/video/{video_choice}"
    out = f"assets/temp/{thread_id}/background.mp4"
    start_time_video, end_time_video = get_start_and_end_times(
        video_length, _probe_duration(src)
    )
    # ffmpeg stream-copy (fast) instead of moviepy re-encode
    result = subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_time_video), "-to", str(end_time_video),
        "-i", src, "-c", "copy", "-avoid_negative_ts", "make_zero", out,
    ], capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg background extraction failed: {stderr[-500:]}")
    print_substep("Background video chopped successfully!", style="bold green")
    return background_config["video"][2]


# Create a tuple for downloads background (background_audio_options, background_video_options)
background_options = load_background_options()
