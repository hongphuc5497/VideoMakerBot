# CLAUDE.md — VideoMakerBot Development Guide

## Project Overview

**VideoMakerBot** — Automated short-form video creator from social media content.

**Status:** Production-ready, actively maintained (v3.4.0)
**Language:** Python 3.10 (locked by `Dockerfile`; host venv may use 3.14 for tooling only)
**Runtime:** **Docker only** — all CLI, GUI, and test invocations go through `docker compose`. Do not invoke `python` on the host.
**Platforms:** Reddit (PRAW API), Threads (Graph API + Web Scraping)

### Core Mission
Transforms social media threads (post + comments/replies) into complete short-form videos with:
- AI-generated speech (7+ TTS providers)
- UI screenshots (Playwright, headless Chromium pre-installed in image)
- Background video/audio overlays
- FFmpeg composition & output (Linux ffmpeg with full filter set, including `drawtext`)
- Optional YouTube upload
- Modern web UI (Tailwind CSS + DaisyUI + Lucide + vanilla ES6) on `localhost:4000`

---

## Architecture at a Glance

```
main.py (CLI)
    ↓ [platform factory]
    ├─→ reddit/subreddit.py [PRAW API]
    └─→ platforms/threads/
        ├─→ fetcher.py [Graph API — your own posts]
        ├─→ scraper.py [Web scraping — trending For You feed]
        └─→ auth.py [Shared Playwright login + cookies]
            ↓ [standard data dict]
            ├─→ TTS/engine_wrapper.py [7+ providers, auto-fallback]
            ├─→ screenshot_downloader.py (Reddit)
            │   or platforms/threads/screenshot.py (Threads)
            ├─→ video_creation/background.py [local or yt-dlp]
            ├─→ video_creation/youtube_uploader.py [optional auto-upload]
            └─→ video_creation/final_video.py [FFmpeg with libx264]
                ↓
                results/{category}/{video.mp4}
```

---

## Data Contract: The "content_object" Dict

All fetchers return this shape:

```python
{
    "thread_id":       str,           # Used for temp folder: assets/temp/{id}/
    "thread_category": str,           # "reddit", "threads" → output folder
    "thread_title":    str,           # TTS + output filename (clean, no metadata)
    "thread_url":      str,           # Playwright navigates here for screenshot
    "is_nsfw":         bool,
    "comments": [
        {
            "comment_body": str,      # TTS per reply (clean body text)
            "comment_url":  str,      # Playwright navigates here
            "comment_id":   str,      # Unique identifier (URL-based for scraper)
        }
    ],
    "thread_post":     str | list,    # Story mode (no comments)
}
```

---

## File Organization

```
VideoMakerBot/
├── platforms/
│   ├── __init__.py                    # Factory: get_content_object(), get_screenshot_fn()
│   └── threads/
│       ├── auth.py                    # Shared Playwright login + cookie management
│       ├── fetcher.py                 # Graph API → content_object (your own posts)
│       ├── scraper.py                 # Web scraping → content_object (trending feed)
│       └── screenshot.py             # Playwright Threads screenshotter (div-based)
│
├── reddit/
│   └── subreddit.py                  # PRAW API → content_object
│
├── video_creation/
│   ├── final_video.py                # FFmpeg composition (libx264, no drawtext on macOS)
│   ├── background.py                 # Video/audio downloader (local files or yt-dlp)
│   ├── screenshot_downloader.py      # Playwright Reddit UI capturer
│   ├── voices.py                     # TTS orchestrator
│   └── youtube_uploader.py           # YouTube OAuth2 upload (post-render hook)
│
├── TTS/
│   ├── engine_wrapper.py             # Provider abstraction + TikTok→pyttsx3 fallback
│   ├── TikTok.py                     # TikTok TTS (hardened error handling)
│   └── ...                           # 7+ provider implementations
│
├── utils/
│   ├── settings.py                   # Config loading + interactive validation
│   ├── videos.py                     # check_done() + check_done_by_id()
│   ├── console.py                    # Rich terminal output
│   ├── .config.template.toml         # Config schema
│   ├── background_videos.json        # Background video manifest
│   ├── background_audios.json        # Background audio manifest
│   └── ...
│
├── GUI/                              # Flask templates (Tailwind + DaisyUI + Lucide)
│   ├── layout.html                   # Base layout (no jQuery, no Bootstrap)
│   ├── index.html                    # Video Library (3 buttons: source / download / copy link)
│   ├── backgrounds.html              # Background Manager (videos catalog)
│   ├── settings.html                 # Config editor (validated against template)
│   └── create.html                   # Render progress page
│
├── tests/
│   └── test_gui_utils.py             # pytest regression for add/delete background
│
├── main.py                           # CLI entry (platform-routed via factory)
├── GUI.py                            # Flask web UI; `/video/<id>` serves files with sanitized headers
├── Dockerfile                        # python:3.10-slim-bookworm + ffmpeg + playwright + pytest
├── docker-compose.yml                # Services: gui, cli, test
├── docker-entrypoint.sh              # Runs `utils.docker_bootstrap` then exec's the command
├── requirements.txt
└── CLAUDE.md
```

---

## Configuration

### Threads (full config)

```toml
[settings]
platform = "threads"

[threads]
discovery_method = "scrape"    # "api" (Graph API, own posts) or "scrape" (trending feed)

[threads.creds]
username = "your_insta"        # For Playwright login (always needed)
password = "your_password"
access_token = ""              # Only for discovery_method="api"
user_id = ""                   # Only for discovery_method="api"

[threads.thread]
post_id = ""                   # Specific post ID; blank = auto-pick from feed
max_reply_length = 500
min_reply_length = 1
min_replies = 5                # Minimum replies for post eligibility
min_engagement = 0             # Minimum likes+reposts for viral filter (0=disabled, 10000=viral)
blocked_words = ""

[settings.tts]
voice_choice = "googletranslate"  # Best for macOS: no API key, fast, free
# voice_choice = "tiktok"         # Needs tiktok_sessionid; auto-falls back to pyttsx3
# voice_choice = "OpenAI"         # Needs openai_api_key

[settings.background]
background_video = "minecraft"
background_audio = "lofi"
background_audio_volume = 0.15
```

### Reddit (reference)

```toml
[settings]
platform = "reddit"

[reddit.creds]
client_id = "..."
client_secret = "..."
username = "..."
password = "..."
2fa = false
2fa_secret = ""               # TOTP base32 secret for auto-2FA

[reddit.thread]
subreddit = "AskReddit"
min_comments = 20
```

### YouTube upload

```toml
[youtube]
enabled = false                # Set true to auto-upload after render
privacy = "public"             # or "private", "unlisted"
client_secret_path = ""        # Path to youtube_client_secret.json
```

---

## Platform-Specific Knowledge

### Threads — Web Scraping (discovery_method = "scrape")

**DOM Structure:**
- Threads.net uses **div-based card layout** — NO `<article>` elements anywhere
- Feed posts: `a[href*="/post/"]` links inside `<div>` cards (class contains `x1a2a7pz`)
- Post pages: same structure; main post link appears first, replies follow
- Screenshots: Use `a[href*="/post/"]` → ancestor div card, NOT `page.locator("article")`

**Card Text Format (used by `_parse_card_text()`):**
```
Line 0:   username
Line 1:   timestamp (e.g., "14h", "1d")
Line 2..N: post body text
Last 1-4: engagement metrics (likes, replies, reposts, quotes)
```

**Engagement Parsing:**
- Numbers can be plain ("266") or abbreviated ("1K", "2.5M")
- `likes` = first trailing number, `replies` = second, `reposts` = third
- `min_engagement` filters by `likes + reposts` total
- Posts are sorted by engagement descending before selection

**Login Flow:**
- Threads uses Instagram auth (`threads.net/login`)
- Selectors: `input[autocomplete="username"]`, `input[autocomplete="current-password"]`
- Button: `get_by_role("button", name="Log in", exact=True).first`
- Cookies cached at `video_creation/data/cookie-threads.json`
- Login logic is shared via `platforms/threads/auth.py`

**API Limitation:**
- Graph API v1.0 only accesses YOUR OWN posts — no trending/discovery
- Scraping bypasses this entirely — no API token needed

### Threads — Graph API (discovery_method = "api")

- Auth: Bearer token, 60-day expiry
- Only accesses authenticated user's own threads + replies
- Use when you have your own content with replies

### Reddit

- **API:** PRAW (Python Reddit API Wrapper)
- **Post discovery:** `subreddit.hot(limit=25)` → `get_subreddit_undone()` → fallback to `top(day/hour/month/week/year/all)`
- **Screenshot:** Playwright on new.reddit.com
- **2FA:** Auto-TOTP via `pyotp` when `2fa_secret` is configured in config.toml

---

## Development Guidelines

### ✅ DO:

1. **Run everything through Docker** — `docker compose up gui`, `docker compose run --rm cli`, `docker compose run --rm test`
2. **Use platform factory** — never import platform modules directly
3. **Return standard content_object** from all fetchers
4. **Use clean body text** for TTS — parse out username/timestamp metadata
5. **Default to `googletranslate` TTS** for headless containers — no API key, fast, free
6. **Use `libx264` encoder** — `h264_nvenc` is NVIDIA-only and not available in the slim image
7. **Test both Threads discovery methods:** `api` and `scrape`
8. **Bind-mount preserves state** — edits to `config.toml`, `results/`, `assets/temp/`, `video_creation/data/`, and the `utils/background_*.json` catalogs persist across container runs
9. **GUI must bind to `0.0.0.0`** in Docker (already enforced via `GUI_HOST=0.0.0.0` env)
10. **Use `/video/<id>` to serve renders** — the route looks up the file by id in `videos.json`, sanitizes the `Content-Disposition` filename, and avoids 404s caused by literal newlines in titles

### ❌ DON'T:

1. **Don't run `python GUI.py` or `python main.py` on the host** — Docker is the only supported path
2. **Don't use `<article>` selectors** on Threads.net — the DOM is div-based
3. **Don't hardcode `h264_nvenc`** — use `libx264` for cross-platform compatibility
4. **Don't import platform modules directly** in main.py/utils
5. **Don't assume config keys exist** without `.get()` fallback
6. **Don't reintroduce jQuery, Bootstrap, or ClipboardJS** — the UI is vanilla ES6 + Tailwind + DaisyUI + Lucide
7. **Don't write to `utils/backgrounds.json`** — it is a legacy empty file. Use `utils/background_videos.json` and `utils/background_audios.json`

---

## Web UI (Flask, served by `gui` service)

- **Stack:** Tailwind CSS, DaisyUI, Lucide Icons, vanilla ES6 (no jQuery, no Bootstrap, no ClipboardJS)
- **Routes:**
  - `/` — Video Library; cards show source-post link, download, and copy-link buttons
  - `/video/<id>` — serves the rendered mp4 by id (lookup via `videos.json`); guards path-traversal and sanitizes the filename for `Content-Disposition`
  - `/backgrounds` — Background Manager UI
  - `/backgrounds.json` — serves `utils/background_videos.json` (the videos catalog)
  - `/background/add`, `/background/delete` — POST endpoints; mutate **both** `utils/background_videos.json` and the `settings.background.background_video.options` array in `utils/.config.template.toml`
  - `/settings` — config editor; loads from `config.toml`, validates against `utils/.config.template.toml`, persists via `utils/gui_utils.modify_settings` (preserves comments/formatting via `tomlkit`)
- **HTML escaping:** the `h()` helper in `index.html` escapes `& " < >` for any user-controlled string embedded in attributes — use it for any new dynamic data on the Library page

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `main.py` | CLI entry; pipeline orchestration via factory |
| `platforms/__init__.py` | Factory dispatch (platform + discovery_method) |
| `platforms/threads/scraper.py` | **NEW** — Web scraping fetcher with engagement parsing |
| `platforms/threads/auth.py` | **NEW** — Shared Playwright login + cookie management |
| `platforms/threads/fetcher.py` | Graph API client (own posts only) |
| `platforms/threads/screenshot.py` | Div-based Threads screenshotter |
| `video_creation/final_video.py` | FFmpeg composition (libx264, platform-aware output) |
| `video_creation/background.py` | Background downloader (local files + yt-dlp) |
| `video_creation/youtube_uploader.py` | **NEW** — OAuth2 YouTube upload |
| `TTS/engine_wrapper.py` | TTS provider abstraction + TikTok fallback |
| `TTS/TikTok.py` | Hardened TikTok TTS with graceful error handling |
| `reddit/subreddit.py` | PRAW Reddit fetcher with auto-2FA |
| `utils/settings.py` | Config loading + interactive validation |
| `utils/videos.py` | Video dedup tracking |
| `utils/.config.template.toml` | Config schema (also drives Settings page validation) |
| `utils/background_videos.json` | Background video manifest (served at `/backgrounds.json`) |
| `utils/background_audios.json` | Background audio manifest |
| `utils/gui_utils.py` | `add_background`, `delete_background`, `modify_settings`, `get_checks` |
| `GUI.py` | Flask app: `/`, `/video/<id>`, `/backgrounds`, `/settings`, `/create` |
| `Dockerfile` | python:3.10-slim-bookworm + ffmpeg + Playwright Chromium + pytest |
| `docker-compose.yml` | Three services: `gui` (port 4000), `cli`, `test` |
| `tests/test_gui_utils.py` | Pytest regression for Background Manager round-trip |

---

## Debugging Tips

### FFmpeg "Unknown encoder 'h264_nvenc'"
→ Use `libx264`. Find-and-replace `h264_nvenc` → `libx264` in `video_creation/final_video.py`. The slim image does not ship with NVIDIA encoders.

### yt-dlp "Requested format is not available"
→ Bump the pinned version in `requirements.txt` and rebuild (`docker compose build`). Also prefer `best[height<=1080]` over `bestvideo` in `video_creation/background.py` — many videos lack video-only streams.

### Threads screenshots fail ("Main post article not found")
→ Threads.net uses div cards, not `<article>`. Ensure screenshot code uses `a[href*="/post/"]` → ancestor div approach.

### Config validator EOFError in non-interactive mode
→ `check_toml()` prompts for ALL platform sections regardless of `platform` setting. Either fill all required fields, edit through `/settings`, or pre-populate `config.toml` before `docker compose run cli`.

### Playwright timeout on Threads login
→ Cookies corrupted. Delete `video_creation/data/cookie-threads.json` for fresh login (the file is bind-mounted, so deleting on host clears the container too). Also confirm selectors: button uses `exact=True` due to multiple "Log in" buttons.

### No viral posts found
→ Lower `min_engagement` in config. Most Threads feed posts have <100 likes — 10000 filters almost everything.

### Background Manager grid is empty
→ `/backgrounds.json` must serve `utils/background_videos.json` (split catalog), **not** the legacy `utils/backgrounds.json` (empty `{}`). Verify in `GUI.py:backgrounds_json`.

### `/video/<id>` returns 404
→ The route looks up the entry in `video_creation/data/videos.json` by `id` and resolves the file under `results/<thread_category>/<filename>.mp4`. Confirm both the JSON entry and the file exist; the file may have been pruned.

### JS "Unexpected end of input" on Library page
→ Any user-controlled string interpolated into an HTML attribute must go through the `h()` helper in `index.html`. Avoid inline `onclick=` with `${JSON.stringify(...)}`.

### Stale image after editing `requirements.txt` or `Dockerfile`
→ `docker compose build` to rebuild. Code changes alone do NOT need a rebuild because the repo root is bind-mounted to `/app`.

---

## Useful Commands (Docker-only)

```bash
# Build (or rebuild after Dockerfile / requirements.txt changes)
docker compose build

# Run the GUI (foreground)
docker compose up gui
# → http://localhost:4000

# Run the GUI in the background
docker compose up -d gui
docker compose logs -f gui
docker compose down

# Run the CLI pipeline (one-off, removed on exit)
docker compose run --rm cli
docker compose run --rm cli python main.py <post_id>

# Run the test suite
docker compose run --rm test

# Open a shell in a fresh container for ad-hoc commands
docker compose run --rm --entrypoint /bin/bash gui
# inside:  python -m py_compile main.py platforms/threads/scraper.py

# Tail a running GUI container
docker compose exec gui ls /app/results/threads/
```

> Anything that needs `pip install`, `playwright install`, or `apt-get` belongs in `Dockerfile` followed by `docker compose build` — never run those on the host.
