# CLAUDE.md — VideoMakerBot Development Guide

## Project Overview

**VideoMakerBot** — Automated short-form video creator from social media content.

**Status:** Production-ready, actively maintained (v3.4.0)
**Language:** Python 3.10+
**Platforms:** Reddit (PRAW API), Threads (Graph API + Web Scraping)

### Core Mission
Transforms social media threads (post + comments/replies) into complete short-form videos with:
- AI-generated speech (7+ TTS providers)
- UI screenshots (Playwright)
- Background video/audio overlays
- FFmpeg composition & output
- Optional YouTube upload

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
├── main.py                           # CLI entry (platform-routed via factory)
├── GUI.py                            # Flask web UI (localhost:4000)
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

1. **Use platform factory** — never import platform modules directly
2. **Return standard content_object** from all fetchers
3. **Use clean body text** for TTS — parse out username/timestamp metadata
4. **Default to `googletranslate` TTS on macOS** — pyttsx3 hangs in headless environments
5. **Use `libx264` encoder on macOS** — `h264_nvenc` is NVIDIA-only
6. **Test both Threads discovery methods:** `api` and `scrape`

### ❌ DON'T:

1. **Don't use `<article>` selectors** on Threads.net — the DOM is div-based
2. **Don't hardcode `h264_nvenc`** — use `libx264` for cross-platform compatibility
3. **Don't rely on `drawtext` FFmpeg filter** — not available in Homebrew builds
4. **Don't import platform modules directly** in main.py/utils
5. **Don't assume config keys exist** without `.get()` fallback

---

## macOS-Specific Notes

- **TTS:** `googletranslate` (gTTS) is the most reliable — free, fast, no API key
  - `tiktok` auto-falls back to `pyttsx3` if sessionid missing, but pyttsx3 is very slow
  - `pyttsx3` works but takes ~60s to initialize NSSpeechSynthesizer
- **FFmpeg encoder:** MUST use `libx264` — `h264_nvenc` is NVIDIA GPU only
- **FFmpeg filters:** `drawtext` missing from Homebrew bottle — credit text is disabled
- **yt-dlp:** Keep updated (`pip install --upgrade yt-dlp`) — YouTube changes APIs frequently
  - Format selector: `best[height<=1080]` not `bestvideo` (many videos lack video-only streams)
  - Upgrade path: `pip install --upgrade yt-dlp`

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
| `utils/.config.template.toml` | Config schema |
| `utils/background_videos.json` | Background video manifest |
| `utils/background_audios.json` | Background audio manifest |

---

## Debugging Tips

### FFmpeg "Unknown encoder 'h264_nvenc'"
→ On macOS, change to `libx264`. Find-and-replace `h264_nvenc` → `libx264` in `video_creation/final_video.py`.

### FFmpeg "No such filter: 'drawtext'"
→ Homebrew FFmpeg lacks drawtext. The credit text overlay is automatically skipped.

### yt-dlp "Requested format is not available"
→ Update yt-dlp: `pip install --upgrade yt-dlp`. Also change format selector from `bestvideo` to `best` in `video_creation/background.py`.

### pyttsx3 hang on macOS
→ NSSpeechSynthesizer needs GUI session. Switch to `voice_choice = "googletranslate"` for headless use.

### Threads screenshots fail ("Main post article not found")
→ Threads.net uses div cards, not `<article>`. Ensure screenshot code uses `a[href*="/post/"]` → ancestor div approach.

### Config validator EOFError in non-interactive mode
→ `check_toml()` prompts for ALL platform sections regardless of `platform` setting. Fill ALL required fields or load config directly with `toml.load()` + `settings.config = ...`.

### Playwright timeout on Threads login
→ Cookies corrupted. Delete `video_creation/data/cookie-threads.json` for fresh login. Also check button selector: must use `exact=True` due to multiple "Log in" buttons.

### No viral posts found
→ Lower `min_engagement` in config. Most Threads feed posts have <100 likes — 10000 filters almost everything.

---

## Useful Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI
python3 main.py

# Run bypassing config validator (non-interactive)
python3 -c "
import sys, toml
sys.path.insert(0, '.')
from utils import settings
settings.config = toml.load('config.toml')
from main import main; main()
"

# Update yt-dlp (YouTube downloads fix)
pip install --upgrade yt-dlp

# Check syntax
python3 -m py_compile main.py platforms/threads/scraper.py

# Run Flask GUI
python3 GUI.py
```
