"""
YouTube Uploader — OAuth2-authenticated upload to YouTube.

Imports the upload logic pattern from vendor/FullyAutomatedRedditVideoMakerBot/uploaders/youtubeUpload.py
but is a standalone reimplementation that:
  - Reads config from the [youtube] section of config.toml
  - Lets the user point to their youtube_client_secret.json via config
  - Caches OAuth2 tokens to video_creation/data/YTtoken.json
  - Derives title, description, tags, privacy, category from config
  - Handles missing dependencies and missing secret files gracefully
"""

import os
import sys

from utils.console import print_markdown, print_step, print_substep

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = os.path.join("video_creation", "data", "YTtoken.json")


def _get_authenticated_service(client_secret_path):
    """
    Authenticate with YouTube via OAuth2.

    Returns a googleapiclient.discovery.Resource (youtube v3) or None on failure.
    """
    # Lazy imports so missing dependencies don't crash the pipeline
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        import google.auth.transport.requests
    except ImportError:
        print_substep(
            "YouTube upload requires google-auth-oauthlib and google-api-python-client.\n"
            "Install them with:  pip install google-auth-oauthlib google-api-python-client",
            "bold red",
        )
        return None

    # Validate client secret file exists
    if not client_secret_path or not os.path.isfile(client_secret_path):
        print_substep(
            f"YouTube client secret not found at: '{client_secret_path}'.\n"
            "Set youtube.client_secret_path in config.toml to the path of your "
            "youtube_client_secret.json file (downloaded from Google Cloud Console).",
            "bold red",
        )
        return None

    credentials = None

    # Load previously cached token if available
    if os.path.isfile(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                credentials = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            credentials = None

    # Refresh expired token or start fresh OAuth flow
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(google.auth.transport.requests.Request())
            except Exception:
                credentials = None

        if not credentials:
            try:
                print_substep(
                    "Opening browser for YouTube OAuth2 authorization...",
                    "blue",
                )
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secret_path, SCOPES
                )
                credentials = flow.run_local_server(port=0)
            except Exception as e:
                print_substep(f"YouTube OAuth2 authentication failed: {e}", "bold red")
                return None

        # Cache credentials for future runs
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(credentials.to_json())
        print_substep("YouTube credentials cached to video_creation/data/YTtoken.json", "green")

    return build("youtube", "v3", credentials=credentials)


def upload_to_youtube(video_path, video_title, config):
    """
    Upload a video to YouTube using settings from the [youtube] config section.

    The function is safe to call even when youtube is disabled — it will
    return None immediately with a log message.

    Args:
        video_path:  Absolute or relative path to the .mp4 video file.
        video_title: Display title for the YouTube video (typically the
                     thread title from the content object).
        config:      Full application configuration dict (settings.config).

    Returns:
        str — YouTube URL (https://youtu.be/VIDEO_ID) on success, or
        None if the upload is disabled, skipped, or failed.
    """
    youtube_config = config.get("youtube", {})
    enabled = youtube_config.get("enabled", False)

    if not enabled:
        print_substep(
            "YouTube upload skipped (youtube.enabled = false in config.toml).",
            "yellow",
        )
        return None

    if not os.path.isfile(video_path):
        print_substep(f"Video file not found: {video_path}", "bold red")
        return None

    client_secret_path = youtube_config.get("client_secret_path", "")

    print_step("Uploading video to YouTube...")

    youtube = _get_authenticated_service(client_secret_path)
    if youtube is None:
        return None

    # Build upload metadata from config (with sensible defaults)
    tags_str = youtube_config.get("tags", "shorts, reddit")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    privacy = youtube_config.get("privacy", "public")
    category = youtube_config.get("category", "22")

    description = youtube_config.get(
        "description",
        f"{video_title}\n\n#shorts #short #reddit",
    )

    try:
        from googleapiclient.http import MediaFileUpload

        body = {
            "snippet": {
                "title": video_title,
                "description": description,
                "tags": tags,
                "categoryId": category,
            },
            "status": {
                "privacyStatus": privacy,
                "madeForKids": False,
            },
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print_substep(
                    f"Uploading... {int(status.progress() * 100)}% complete."
                )

        video_url = f"https://youtu.be/{response['id']}"
        print_markdown(f"## Video uploaded successfully: {video_url}")
        return video_url

    except Exception as e:
        print_substep(f"YouTube upload failed: {e}", "bold red")
        return None
