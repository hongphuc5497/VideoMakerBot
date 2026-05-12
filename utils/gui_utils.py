import json
import re
from pathlib import Path

import toml
import tomlkit
from flask import flash


MASKED_SECRET_VALUE = "********"
SENSITIVE_SETTING_PARTS = {
    "password",
    "client_secret",
    "access_token",
    "2fa_secret",
    "tiktok_sessionid",
    "elevenlabs_api_key",
    "openai_api_key",
}


def is_sensitive_setting(name: str) -> bool:
    return any(part in name for part in SENSITIVE_SETTING_PARTS)


# Get validation checks from template, keyed by dotted path
# (e.g. "reddit.creds.username", "threads.creds.username") so that
# leaf-key collisions across platform sections don't clobber each other.
def get_checks():
    template = toml.load("utils/.config.template.toml")
    checks = {}

    def unpack_checks(obj: dict, path):
        for key in obj.keys():
            full = f"{path}.{key}" if path else key
            if isinstance(obj[key], dict) and "optional" in obj[key].keys():
                checks[full] = obj[key]
            elif isinstance(obj[key], dict):
                unpack_checks(obj[key], full)

    unpack_checks(template, "")

    return checks


# Get current config (from config.toml) as a dict keyed by dotted path.
# Mirrors the path layout of get_checks() so the GUI can match values to checks.
def get_config(obj: dict, done=None, path=""):
    if done is None:
        done = {}
    for key in obj.keys():
        full = f"{path}.{key}" if path else key
        if not isinstance(obj[key], dict):
            done[full] = obj[key]
        else:
            get_config(obj[key], done, full)

    return done


# Checks if value is valid
def check(value, checks):
    incorrect = False

    if value == "False":
        value = ""

    if not incorrect and "type" in checks:
        try:
            value = {"int": int, "float": float, "bool": bool, "str": str}.get(checks["type"], str)(value)
        except (ValueError, TypeError):
            incorrect = True

    if (
        not incorrect and "options" in checks and value not in checks["options"]
    ):  # FAILSTATE Value isn't one of the options
        incorrect = True
    if (
        not incorrect
        and "regex" in checks
        and (
            (isinstance(value, str) and re.match(checks["regex"], value) is None)
            or not isinstance(value, str)
        )
    ):  # FAILSTATE Value doesn't match regular expression, or has regular expression but isn't a string.
        incorrect = True

    if (
        not incorrect
        and not hasattr(value, "__iter__")
        and (
            ("nmin" in checks and checks["nmin"] is not None and value < checks["nmin"])
            or ("nmax" in checks and checks["nmax"] is not None and value > checks["nmax"])
        )
    ):
        incorrect = True

    if (
        not incorrect
        and hasattr(value, "__iter__")
        and (
            ("nmin" in checks and checks["nmin"] is not None and len(value) < checks["nmin"])
            or ("nmax" in checks and checks["nmax"] is not None and len(value) > checks["nmax"])
        )
    ):
        incorrect = True

    if incorrect:
        return "Error"

    return value


# Modify settings (after the form is submitted)
def modify_settings(data: dict, config_load, checks: dict):
    # Walk the dotted path and set the value at the precise location.
    # Example: "reddit.creds.username" -> config_load["reddit"]["creds"]["username"]
    def set_by_path(obj: dict, dotted_path: str, value):
        parts = dotted_path.split(".")
        cursor = obj
        for part in parts[:-1]:
            if part not in cursor or not isinstance(cursor[part], dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = value

    # Filter data to only include keys present in checks
    data = {key: value for key, value in data.items() if key in checks.keys()}

    # Validate and apply values
    for name, raw_value in data.items():
        if is_sensitive_setting(name) and raw_value == MASKED_SECRET_VALUE:
            continue

        value = check(raw_value, checks[name])

        # Value is invalid
        if value == "Error":
            flash("Some values were incorrect and didn't save!", "error")
        else:
            # Value is valid
            set_by_path(config_load, name, value)

    # Save changes in config.toml
    with Path("config.toml").open("w") as toml_file:
        toml_file.write(tomlkit.dumps(config_load))

    flash("Settings saved!")

    return get_config(config_load)


# Delete background video
def delete_background(key):
    # Read background catalog
    with open("utils/background_videos.json", "r", encoding="utf-8") as backgrounds:
        data = json.load(backgrounds)

    if data.pop(key, None) is None:
        flash("Couldn't find this background. Try refreshing the page.", "error")
        return

    with open("utils/background_videos.json", "w", encoding="utf-8") as backgrounds:
        json.dump(data, backgrounds, ensure_ascii=False, indent=4)

    # Remove background video from ".config.template.toml"
    config = tomlkit.loads(Path("utils/.config.template.toml").read_text())
    options = config["settings"]["background"]["background_video"]["options"]
    if key in options:
        options.remove(key)

    with Path("utils/.config.template.toml").open("w") as toml_file:
        toml_file.write(tomlkit.dumps(config))

    flash(f'Successfully removed "{key}" background!')


# Add background video
def add_background(youtube_uri, filename, citation, position):
    # Validate YouTube URI
    regex = re.compile(r"(?:\/|%3D|v=|vi=)([0-9A-Za-z_-]{11})(?:[%#?&]|$)").search(youtube_uri)

    if not regex:
        flash("YouTube URI is invalid!", "error")
        return

    youtube_uri = f"https://www.youtube.com/watch?v={regex.group(1)}"

    # Check if the position is valid
    if position == "" or position == "center":
        position = "center"

    elif position.isdecimal():
        position = int(position)

    else:
        flash('Position is invalid! It can be "center" or decimal number.', "error")
        return

    # Sanitize citation to prevent path traversal
    citation = re.sub(r"[./\\]", "_", citation)
    regex = re.compile(r"^([a-zA-Z0-9\s_-]{1,100})$").match(filename)

    if not regex:
        flash("Filename is invalid!", "error")
        return

    filename = filename.replace(" ", "_")

    # Check if the background doesn't already exist
    with open("utils/background_videos.json", "r", encoding="utf-8") as backgrounds:
        data = json.load(backgrounds)

        # Check if key isn't already taken
        if filename in list(data.keys()):
            flash("Background video with this name already exist!", "error")
            return

        # Check if the YouTube URI isn't already used under different name
        if youtube_uri in [data[i][0] for i in list(data.keys()) if i != "__comment"]:
            flash("Background video with this YouTube URI is already added!", "error")
            return

    # Add background video to json file
    with open("utils/background_videos.json", "r+", encoding="utf-8") as backgrounds:
        data = json.load(backgrounds)

        data[filename] = [youtube_uri, filename + ".mp4", citation, position]
        backgrounds.seek(0)
        backgrounds.truncate()
        json.dump(data, backgrounds, ensure_ascii=False, indent=4)

    # Add background video to ".config.template.toml"
    config = tomlkit.loads(Path("utils/.config.template.toml").read_text())
    options = config["settings"]["background"]["background_video"]["options"]
    if filename not in options:
        options.append(filename)

    with Path("utils/.config.template.toml").open("w") as toml_file:
        toml_file.write(tomlkit.dumps(config))

    flash(f'Added "{citation}-{filename}.mp4" as a new background video!')

    return


# Delete videos by ID list — removes entries from videos.json and mp4 files from disk.
# Returns the number of files actually removed from disk.
def delete_videos(ids):
    ids = set(ids)
    videos_path = Path("video_creation/data/videos.json")
    results_root = Path("results").resolve()

    with videos_path.open("r", encoding="utf-8") as f:
        videos = json.load(f)

    to_delete = {v["id"]: v for v in videos if v.get("id") in ids}
    remaining = [v for v in videos if v.get("id") not in ids]

    deleted = 0
    for entry in to_delete.values():
        subreddit = entry.get("subreddit", "")
        filename = entry.get("filename", "")
        if subreddit and filename:
            try:
                file_path = (results_root / subreddit / filename).resolve()
                file_path.relative_to(results_root)  # path-traversal guard
                if file_path.exists():
                    file_path.unlink()
                    deleted += 1
            except (ValueError, OSError):
                pass

    with videos_path.open("w", encoding="utf-8") as f:
        json.dump(remaining, f, ensure_ascii=False, indent=4)

    return deleted
