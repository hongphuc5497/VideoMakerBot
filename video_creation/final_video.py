import json
import os
import re
import subprocess
import tempfile
import textwrap
import threading
import time
from os.path import exists
from pathlib import Path
from typing import Dict, Final, Tuple

import av
import translators
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
from rich.progress import track

from utils import settings
from utils.cleanup import cleanup
from utils.console import print_step, print_substep
from utils.fonts import getheight
from utils.id import extract_id
from utils.thumbnail import create_thumbnail
from utils.videos import save_data

console = Console()


def _probe_duration(path: str) -> float:
    """Get media duration in seconds using PyAV."""
    with av.open(path) as container:
        stream = container.streams[0]
        return float(stream.duration * stream.time_base)


def _run_ffmpeg(args: list[str], description: str = "") -> None:
    """Run ffmpeg subprocess with error handling."""
    result = subprocess.run(
        ["ffmpeg", "-y"] + args,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg {description} failed: {stderr[-500:]}")


class ProgressFfmpeg(threading.Thread):
    """Thread that reads ffmpeg progress via a named pipe during encoding."""

    def __init__(self, vid_duration_seconds, progress_update_callback):
        threading.Thread.__init__(self, name="ProgressFfmpeg")
        self.stop_event = threading.Event()
        self.output_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
        self.vid_duration_seconds = vid_duration_seconds
        self.progress_update_callback = progress_update_callback

    def run(self):
        while not self.stop_event.is_set():
            latest_progress = self._get_latest_ms_progress()
            if latest_progress is not None:
                completed_percent = latest_progress / self.vid_duration_seconds
                self.progress_update_callback(min(completed_percent, 1.0))
            time.sleep(1)

    def _get_latest_ms_progress(self):
        try:
            with open(self.output_file.name) as f:
                lines = f.readlines()
        except (IOError, OSError):
            return None
        if lines:
            for line in lines:
                if "out_time_ms" in line:
                    val = line.split("=")[1].strip()
                    if val.isnumeric():
                        return float(val) / 1000000.0
        return None

    def stop(self):
        self.stop_event.set()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()
        try:
            os.unlink(self.output_file.name)
        except OSError:
            pass


def name_normalize(name: str) -> str:
    name = re.sub(r'[?\\"%*:|<>]', "", name)
    name = re.sub(r"( [w,W]\s?\/\s?[o,O,0])", r" without", name)
    name = re.sub(r"( [w,W]\s?\/)", r" with", name)
    name = re.sub(r"(\d+)\s?\/\s?(\d+)", r"\1 of \2", name)
    name = re.sub(r"(\w+)\s?\/\s?(\w+)", r"\1 or \2", name)
    name = re.sub(r"\/", r"", name)

    lang = (settings.config["settings"].get("post_lang") or
            settings.config.get("reddit", {}).get("thread", {}).get("post_lang", ""))
    if lang:
        print_substep("Translating filename...")
        return translators.translate_text(name, translator="google", to_language=lang)
    return name


def get_text_height(draw, text, font, max_width):
    lines = textwrap.wrap(text, width=max_width)
    total_height = 0
    for line in lines:
        _, _, _, height = draw.textbbox((0, 0), line, font=font)
        total_height += height
    return total_height


def create_fancy_thumbnail(image, text, text_color, padding, wrap=35):
    print_step(f"Creating fancy thumbnail for: {text}")
    font_title_size = 47
    font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), font_title_size)
    image_width, image_height = image.size

    draw = ImageDraw.Draw(image)
    text_height = get_text_height(draw, text, font, wrap)
    lines = textwrap.wrap(text, width=wrap)
    new_image_height = image_height + text_height + padding * (len(lines) - 1) - 50

    top_part_height = image_height // 2
    middle_part_height = 1
    bottom_part_height = image_height - top_part_height - middle_part_height

    top_part = image.crop((0, 0, image_width, top_part_height))
    middle_part = image.crop((0, top_part_height, image_width, top_part_height + middle_part_height))
    bottom_part = image.crop((0, top_part_height + middle_part_height, image_width, image_height))

    new_middle_height = new_image_height - top_part_height - bottom_part_height
    middle_part = middle_part.resize((image_width, new_middle_height))

    new_image = Image.new("RGBA", (image_width, new_image_height))
    new_image.paste(top_part, (0, 0))
    new_image.paste(middle_part, (0, top_part_height))
    new_image.paste(bottom_part, (0, top_part_height + new_middle_height))

    draw = ImageDraw.Draw(new_image)
    y = top_part_height + padding
    for line in lines:
        draw.text((120, y), line, font=font, fill=text_color, align="left")
        y += get_text_height(draw, line, font, wrap) + padding

    username_font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), 30)
    draw.text(
        (205, 825),
        settings.config["settings"]["channel_name"],
        font=username_font,
        fill=text_color,
        align="left",
    )
    return new_image


def merge_background_audio(tts_audio_path: str, reddit_id: str) -> str:
    """Mix background audio into the TTS audio. Returns path to the mixed file."""
    background_audio_volume = settings.config["settings"]["background"]["background_audio_volume"]
    if background_audio_volume == 0:
        return tts_audio_path

    output_path = f"assets/temp/{reddit_id}/audio_mixed.mp3"
    bg_audio_path = f"assets/temp/{reddit_id}/background.mp3"
    _run_ffmpeg([
        "-i", tts_audio_path,
        "-i", bg_audio_path,
        "-filter_complex",
        f"[1:a]volume={background_audio_volume}[bga];[0:a][bga]amix=inputs=2:duration=longest",
        "-b:a", "192k",
        output_path,
    ], "audio_mix")
    return output_path


def _build_audio_concat_list(input_paths: list[str], list_path: str) -> None:
    """Write a ffmpeg concat demuxer file list."""
    with open(list_path, "w") as f:
        for p in input_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")


def _build_overlay_filter_complex(overlay_items: list[dict], W: int, H: int) -> str:
    """Build a ffmpeg filter_complex string for overlaying images on background.

    Prepends crop+scale on [0:v] so raw background.mp4 can be used directly
    (no separate prepare_background encode pass needed).

    Each overlay item: {path, start_time, duration, opacity, scale_w, scale_h}
    """
    parts = []
    # Crop background to target aspect ratio and scale — merged from prepare_background
    parts.append(f"[0:v]crop=ih*({W}/{H}):ih,scale={W}:{H}[bg];")
    prev_label = "bg"

    for i, item in enumerate(overlay_items):
        scaled_label = f"sc{i}"
        faded_label = f"fd{i}"

        # Scale the overlay image
        parts.append(
            f"[{i + 1}:v]scale={item['scale_w']}:{item['scale_h']}[{scaled_label}];"
        )
        # Set opacity
        parts.append(
            f"[{scaled_label}]colorchannelmixer=aa={item['opacity']}[{faded_label}];"
        )
        # Overlay with timing
        enable = f"between(t,{item['start_time']},{item['start_time'] + item['duration']})"
        next_label = f"out{i}" if i < len(overlay_items) - 1 else "final"
        parts.append(
            f"[{prev_label}][{faded_label}]overlay="
            f"x=(main_w-overlay_w)/2:y=(main_h-overlay_h)/2:"
            f"enable='{enable}'[{next_label}]"
        )
        if i < len(overlay_items) - 1:
            parts.append(";")
        prev_label = next_label

    return "".join(parts)


def make_final_video(
    number_of_clips: int,
    length: int,
    reddit_obj: dict,
    background_config: Dict[str, Tuple],
):
    """Gathers audio clips, stitches screenshots together, encodes final video."""
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])
    opacity = settings.config["settings"]["opacity"]
    reddit_id = extract_id(reddit_obj)

    allowOnlyTTSFolder: bool = (
        settings.config["settings"]["background"]["enable_extra_audio"]
        and settings.config["settings"]["background"]["background_audio_volume"] != 0
    )

    print_step("Creating the final video 🎥")

    # --- Step 1: Background path (crop+scale merged into overlay filter) ---
    background_path = f"assets/temp/{reddit_id}/background.mp4"

    # --- Step 2: Concatenate all TTS audio clips ---
    audio_clip_paths = []
    if number_of_clips == 0 and not settings.config["settings"]["storymode"]:
        print("No audio clips to gather. Please use a different TTS or post.")
        exit()

    if settings.config["settings"]["storymode"]:
        if settings.config["settings"]["storymodemethod"] == 0:
            audio_clip_paths = [
                f"assets/temp/{reddit_id}/mp3/title.mp3",
                f"assets/temp/{reddit_id}/mp3/postaudio.mp3",
            ]
        else:
            audio_clip_paths = [f"assets/temp/{reddit_id}/mp3/title.mp3"]
            for i in range(number_of_clips):
                audio_clip_paths.append(f"assets/temp/{reddit_id}/mp3/postaudio-{i}.mp3")
    else:
        audio_clip_paths = [f"assets/temp/{reddit_id}/mp3/title.mp3"]
        for i in range(number_of_clips):
            audio_clip_paths.append(f"assets/temp/{reddit_id}/mp3/{i}.mp3")

    existing = [p for p in audio_clip_paths if os.path.exists(p)]
    concat_audio_path = f"assets/temp/{reddit_id}/audio.mp3"
    concat_list_path = concat_audio_path + ".concat.txt"
    _build_audio_concat_list(existing, concat_list_path)
    _run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", concat_list_path,
        "-b:a", "192k", concat_audio_path,
    ], "audio_concat")
    os.unlink(concat_list_path)

    # Probe durations
    if not existing:
        raise RuntimeError("No audio clips generated — all TTS segments failed to produce output")
    audio_clips_durations = [_probe_duration(p) for p in existing]

    # --- Step 3: Mix background audio ---
    mixed_audio_path = merge_background_audio(concat_audio_path, reddit_id)

    console.log(f"[bold green] Video Will Be: {length} Seconds Long")

    # --- Step 4: Build overlay items ---
    screenshot_width = int((W * 45) // 100)
    Path(f"assets/temp/{reddit_id}/png").mkdir(parents=True, exist_ok=True)

    platform = settings.config["settings"].get("platform", "reddit")

    # Use actual screenshot for non-Reddit platforms (Threads etc.), Reddit template for Reddit
    title_img_path = f"assets/temp/{reddit_id}/png/title.png"
    if platform == "reddit":
        title_template = Image.open("assets/title_template.png")
        title = reddit_obj["thread_title"]
        title = name_normalize(title)
        title_img = create_fancy_thumbnail(title_template, title, "#000000", 5)
        title_img.save(title_img_path)

    overlay_items = []
    current_time = 0.0

    overlay_items.append({
        "path": title_img_path,
        "start_time": current_time,
        "duration": audio_clips_durations[0],
        "opacity": opacity,
        "scale_w": screenshot_width,
        "scale_h": -1,
    })
    current_time += audio_clips_durations[0]

    if settings.config["settings"]["storymode"]:
        if settings.config["settings"]["storymodemethod"] == 0:
            story_path = f"assets/temp/{reddit_id}/png/story_content.png"
            if os.path.exists(story_path):
                overlay_items.append({
                    "path": story_path,
                    "start_time": current_time,
                    "duration": audio_clips_durations[1] if len(audio_clips_durations) > 1 else 5,
                    "opacity": opacity,
                    "scale_w": screenshot_width,
                    "scale_h": -1,
                })
        elif settings.config["settings"]["storymodemethod"] == 1:
            for i in range(number_of_clips):
                dur_idx = i + 1
                if dur_idx >= len(audio_clips_durations):
                    break
                img_path = f"assets/temp/{reddit_id}/png/img{i}.png"
                if os.path.exists(img_path):
                    overlay_items.append({
                        "path": img_path,
                        "start_time": current_time,
                        "duration": audio_clips_durations[dur_idx],
                        "opacity": opacity,
                        "scale_w": screenshot_width,
                        "scale_h": -1,
                    })
                current_time += audio_clips_durations[dur_idx]
    else:
        for i in range(number_of_clips):
            dur_idx = i + 1  # audio_clips_durations[0] is title, [1..N] are comments
            if dur_idx >= len(audio_clips_durations):
                break
            img_path = f"assets/temp/{reddit_id}/png/comment_{i}.png"
            if os.path.exists(img_path):
                overlay_items.append({
                    "path": img_path,
                    "start_time": current_time,
                    "duration": audio_clips_durations[dur_idx],
                    "opacity": opacity,
                    "scale_w": screenshot_width,
                    "scale_h": -1,
                })
            current_time += audio_clips_durations[dur_idx]

    # --- Step 5: Build filter_complex and render ---
    filter_complex = _build_overlay_filter_complex(overlay_items, W, H)

    title_clean = extract_id(reddit_obj, "thread_title")
    idx = extract_id(reddit_obj)
    title_thumb = reddit_obj["thread_title"]
    filename = f"{name_normalize(title_clean)[:251]}"

    platform = settings.config["settings"].get("platform", "reddit")
    if platform == "reddit":
        subreddit = settings.config["reddit"]["thread"]["subreddit"]
    else:
        subreddit = reddit_obj.get("thread_category", platform)

    if not exists(f"./results/{subreddit}"):
        print_substep("The 'results' folder could not be found so it was automatically created.")
        os.makedirs(f"./results/{subreddit}")

    if not exists(f"./results/{subreddit}/OnlyTTS") and allowOnlyTTSFolder:
        os.makedirs(f"./results/{subreddit}/OnlyTTS")

    # Thumbnail
    settingsbackground = settings.config["settings"]["background"]
    if settingsbackground["background_thumbnail"]:
        if not exists(f"./results/{subreddit}/thumbnails"):
            os.makedirs(f"./results/{subreddit}/thumbnails")
        first_image = next(
            (f for f in os.listdir("assets/backgrounds") if f.endswith(".png")),
            None,
        )
        if first_image:
            font_family = settingsbackground["background_thumbnail_font_family"]
            font_size = settingsbackground["background_thumbnail_font_size"]
            font_color = settingsbackground["background_thumbnail_font_color"]
            thumbnail = Image.open(f"assets/backgrounds/{first_image}")
            width, height = thumbnail.size
            thumbnailSave = create_thumbnail(
                thumbnail, font_family, font_size, font_color, width, height, title_thumb,
            )
            thumbnailSave.save(f"./assets/temp/{reddit_id}/thumbnail.png")
            print_substep(f"Thumbnail - Building Thumbnail in assets/temp/{reddit_id}/thumbnail.png")

    # --- Step 6: Render ---
    defaultPath = f"results/{subreddit}"
    video_output_path = defaultPath + f"/{filename}"
    video_output_path = video_output_path[:251] + ".mp4"

    print_step("Rendering the video 🎥")
    from tqdm import tqdm
    pbar = tqdm(total=100, desc="Progress: ", bar_format="{l_bar}{bar}", unit=" %")

    def on_update_example(progress) -> None:
        status = round(progress * 100, 2)
        old_percentage = pbar.n
        pbar.update(status - old_percentage)

    # Build ffmpeg command: background + overlay images → filter_complex → video only
    ffmpeg_inputs = ["-i", background_path]
    for item in overlay_items:
        ffmpeg_inputs.extend(["-i", item["path"]])

    with ProgressFfmpeg(length, on_update_example) as progress:
        # First pass: render video with overlays (no audio)
        video_only_path = video_output_path + ".video.mp4"
        _run_ffmpeg(
            ffmpeg_inputs + [
                "-filter_complex", filter_complex,
                "-map", "[final]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-progress", progress.output_file.name,
                video_only_path,
            ],
            "overlay_render"
        )

    # Second pass: mux video with audio
    _run_ffmpeg([
        "-i", video_only_path,
        "-i", mixed_audio_path,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-map", "0:v:0", "-map", "1:a:0",
        video_output_path,
    ], "audio_mux")
    os.unlink(video_only_path)

    old_percentage = pbar.n
    pbar.update(100 - old_percentage)

    # OnlyTTS variant
    if allowOnlyTTSFolder:
        only_tts_path = defaultPath + f"/OnlyTTS/{filename}"
        only_tts_path = only_tts_path[:251] + ".mp4"
        only_tts_video = only_tts_path + ".video.mp4"
        print_step("Rendering the Only TTS Video 🎥")
        with ProgressFfmpeg(length, on_update_example) as progress2:
            _run_ffmpeg(
                ffmpeg_inputs + [
                    "-filter_complex", filter_complex,
                    "-map", "[final]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-progress", progress2.output_file.name,
                    only_tts_video,
                ],
                "only_tts_render"
            )
        _run_ffmpeg([
            "-i", only_tts_video,
            "-i", concat_audio_path,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-map", "0:v:0", "-map", "1:a:0",
            only_tts_path,
        ], "only_tts_mux")
        os.unlink(only_tts_video)

    pbar.close()
    save_data(subreddit, filename + ".mp4", title_clean, idx, background_config["video"][2])
    print_step("Removing temporary files 🗑")
    cleanups = cleanup(reddit_id)
    print_substep(f"Removed {cleanups} temporary files 🗑")
    print_step("Done! 🎉 The video is in the results folder 📁")
