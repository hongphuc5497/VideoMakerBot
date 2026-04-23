# CLAUDE.md — VideoMakerBot Development Guide

## Project Overview

**VideoMakerBot** — Automated short-form video creator from social media content.

**Status:** Production-ready, actively maintained (v3.4.0)
**Language:** Python 3.10+
**Platforms:** Reddit (original), Threads (NEW), X/Twitter (planned)

### Core Mission
Transforms social media threads (post + comments/replies) into complete short-form videos with:
- AI-generated speech (7+ TTS providers)
- UI screenshots (Playwright)
- Background video/audio overlays
- FFmpeg composition & output

---

## Architecture at a Glance

```
main.py (CLI)
    ↓ [platform factory]
    ├─→ reddit/subreddit.py [PRAW API]
    └─→ platforms/threads/fetcher.py [Graph API]
        ↓ [standard data dict]
        ├─→ TTS/engine_wrapper.py [7+ providers]
        ├─→ screenshot_downloader.py (Reddit)
        │   or platforms/threads/screenshot.py (Threads)
        ├─→ video_creation/background.py
        └─→ video_creation/final_video.py [FFmpeg]
            ↓
            results/{category}/{video.mp4}
```

### Key Design: Platform Abstraction via Factory Pattern

**Why:** Single codebase supports multiple platforms without tight coupling.

**How:** `platforms/__init__.py` exports:
- `get_content_object(POST_ID=None)` — routes to right fetcher
- `get_screenshot_fn()` — routes to right screenshotter

**Result:** Adding X/Twitter requires only: new module + config section + two `elif` branches.

---

## Data Contract: The "content_object" Dict

All fetchers return this shape (defined in `platforms/__init__.py`):

```python
{
    # Unique identifiers
    "thread_id":       str,           # Used for temp folder: assets/temp/{id}/
    "thread_category": str,           # "reddit", "threads", etc. → output folder

    # Content
    "thread_title":    str,           # TTS as title + output filename
    "thread_url":      str,           # Playwright navigates here for screenshot
    "is_nsfw":         bool,          # Content filter flag

    # Replies/Comments (mutually exclusive with thread_post)
    "comments": [
        {
            "comment_body": str,      # TTS per reply
            "comment_url":  str,      # Playwright navigates here
            "comment_id":   str,      # CSS selector ID or unique identifier
        }
    ],

    # OR Story mode:
    "thread_post":     str | list,    # Long-form text (no comments)
}
```

**Why:** Loose coupling—TTS, backgrounds, and video composition don't need platform-specific logic.

---

## File Organization

```
VideoMakerBot/
├── platforms/                      # Multi-platform abstraction
│   ├── __init__.py                # Factory: get_content_object(), get_screenshot_fn()
│   └── threads/                   # Threads (Meta) implementation
│       ├── fetcher.py             # Graph API → content_object
│       └── screenshot.py          # Playwright Threads screenshotter
│
├── reddit/                        # Reddit implementation (kept as-is)
│   └── subreddit.py              # PRAW API → content_object + thread_category
│
├── video_creation/
│   ├── final_video.py            # FFmpeg composition (platform-aware folder naming)
│   ├── screenshot_downloader.py  # Playwright Reddit UI capturer
│   ├── voices.py                 # TTS orchestrator (platform-agnostic)
│   ├── background.py             # Video/audio downloader (platform-agnostic)
│   └── data/
│       ├── videos.json           # Dedup tracker
│       ├── cookie-dark-mode.json # Reddit theme cookie
│       └── cookie-threads.json   # Threads session cookie (auto-created)
│
├── TTS/                          # Text-to-Speech
│   ├── engine_wrapper.py         # Provider abstraction + post_lang fallback
│   ├── elevenlabs.py, aws_polly.py, etc. # 7+ provider implementations
│
├── utils/
│   ├── settings.py               # Config loading + validation
│   ├── videos.py                 # check_done() + check_done_by_id()
│   ├── console.py                # Rich terminal output
│   ├── .config.template.toml     # Config schema (platform sections)
│   └── ... (id, voice, cleanup, etc.)
│
├── main.py                       # CLI entry (platform-routed via factory)
├── GUI.py                        # Flask web UI (localhost:4000)
├── requirements.txt              # Dependencies
└── CLAUDE.md / AGENT.md          # This file + agent guidelines
```

---

## Configuration

**File:** `utils/.config.template.toml` (schema) → `config.toml` (user config)

### Platform Selection
```toml
[settings]
platform = "reddit"     # or "threads"
post_lang = "es-cr"     # Optional: translation language (all platforms)
```

### Reddit Config
```toml
[reddit.creds]
client_id = "..."       # OAuth app
client_secret = "..."
username = "..."
password = "..."
2fa = true/false

[reddit.thread]
subreddit = "AskReddit"
post_id = ""            # Leave blank for auto-pick
max_comment_length = 500
min_comment_length = 1
min_comments = 20
blocked_words = "..."
```

### Threads Config (NEW)
```toml
[threads.creds]
access_token = "EAABsbCS..."  # Meta Graph API token (60-day expiry)
user_id = "12345678901234567"
username = "your_insta"       # For Playwright login
password = "your_password"

[threads.thread]
post_id = ""            # Leave blank for auto-pick
max_reply_length = 500
min_reply_length = 1
min_replies = 5
blocked_words = "..."
```

### Generic Settings
```toml
[settings]
theme = "dark"
resolution_w = 1080
resolution_h = 1920
storymode = false
times_to_run = 1

[settings.tts]
voice_choice = "tiktok"     # or "elevenlabs", "awspolly", "googletranslate", etc.
random_voice = true
silence_duration = 0.3

[settings.background]
background_video = "minecraft"
background_audio = "lofi"
background_audio_volume = 0.15
```

---

## Development Guidelines

### ✅ DO:

1. **Use platform factory in main.py**
   ```python
   from platforms import get_content_object, get_screenshot_fn
   reddit_object = get_content_object(POST_ID)
   screenshot_fn = get_screenshot_fn()
   screenshot_fn(reddit_object, number_of_comments)
   ```

2. **Return standard content dict** from all fetchers
   ```python
   return {
       "thread_id": ...,
       "thread_category": ...,  # NEW: replaces hardcoded subreddit
       "comments": [...]
   }
   ```

3. **Use config fallback chains** for cross-platform keys
   ```python
   lang = (settings.config["settings"].get("post_lang") or
           settings.config.get("reddit", {}).get("thread", {}).get("post_lang", ""))
   ```

4. **Read thread_category from dict** instead of config
   ```python
   # WRONG:
   subreddit = settings.config["reddit"]["thread"]["subreddit"]

   # RIGHT:
   platform = settings.config["settings"].get("platform", "reddit")
   if platform == "reddit":
       subreddit = settings.config["reddit"]["thread"]["subreddit"]
   else:
       subreddit = reddit_obj.get("thread_category", platform)
   ```

5. **Test both platforms** after core pipeline changes
   ```bash
   # Test Reddit (must not regress)
   sed -i 's/platform = "threads"/platform = "reddit"/' config.toml
   python3 main.py

   # Test Threads
   sed -i 's/platform = "reddit"/platform = "threads"/' config.toml
   python3 main.py --post-id <threads-id>
   ```

### ❌ DON'T:

1. **Don't import platform modules directly** in main.py/utils
   ```python
   # WRONG: from reddit.subreddit import get_subreddit_threads
   # RIGHT: from platforms import get_content_object
   ```

2. **Don't hardcode platform names** in generic modules
   ```python
   # WRONG in final_video.py:
   subreddit = settings.config["reddit"]["thread"]["subreddit"]

   # RIGHT:
   subreddit = reddit_obj.get("thread_category", "unknown")
   ```

3. **Don't add platform-specific UI selectors** outside `platforms/{platform}/screenshot.py`
   - Reddit selectors stay in `video_creation/screenshot_downloader.py`
   - Threads selectors stay in `platforms/threads/screenshot.py`

4. **Don't assume config keys exist** without fallback
   ```python
   # WRONG: lang = settings.config["reddit"]["thread"]["post_lang"]
   # RIGHT: lang = settings.config.get("settings", {}).get("post_lang", "")
   ```

---

## Platform-Specific Knowledge

### Reddit
- **API:** PRAW (Python Reddit API Wrapper)
- **Auth:** OAuth app (client_id, secret) + username/password
- **Screenshot:** Playwright on reddit.com/new.reddit.com
  - Login form: `input[name="username"]`, `input[name="password"]`
  - Post selector: `[data-test-id="post-content"]`
  - Comment selector: `#t1_{comment_id}`
- **NSFW:** `submission.over_18`
- **Output folder:** `results/{subreddit}/`

### Threads
- **API:** Meta Graph API (v18.0+)
- **Auth:** User access token (60-day lifetime) via https://developers.facebook.com/
- **Screenshot:** Playwright on threads.net
  - Login form: `input[autocomplete="username"]`, `input[autocomplete="current-password"]`
  - Post selector: `article` (universal, more stable than Reddit)
  - Cookies saved to: `video_creation/data/cookie-threads.json`
- **NSFW:** API doesn't provide; always False
- **Output folder:** `results/threads/`

### Future: X/Twitter
Create: `platforms/twitter/fetcher.py` + `platforms/twitter/screenshot.py` + config section
Update: `platforms/__init__.py` with `elif platform == "twitter"` branches

---

## Extending the Project

### Adding a New TTS Provider
1. Create `TTS/my_provider.py` with a class implementing the TTS interface
2. Add config keys to `[settings.tts]` in `.config.template.toml`
3. Update `TTS/engine_wrapper.py` to call your provider
4. Test with `settings.config["settings"]["tts"]["voice_choice"] = "my_provider"`

### Adding a New Platform (e.g., X/Twitter)
1. **Create fetcher:** `platforms/twitter/fetcher.py`
   - Implement `get_twitter_content(POST_ID=None)` returning standard dict
2. **Create screenshotter:** `platforms/twitter/screenshot.py`
   - Implement `get_screenshots_of_twitter_posts(content_object, screenshot_num)`
3. **Update config:** Add `[twitter.creds]` and `[twitter.thread]` sections
4. **Update factory:** Add `elif platform == "twitter"` in `platforms/__init__.py`
5. **Update CLI helper:** Add case to `_get_platform_post_id()` in `main.py`
6. **Test:** Verify Reddit mode still works, test Twitter mode end-to-end

**Zero changes needed to:** TTS, backgrounds, video composition, or utils.

---

## Debugging Tips

### "No matching distribution found for yt-dlp==2026.3.17"
→ yt-dlp uses date versioning (YYYY.M.DD, no leading zeros). Use `2025.10.14` (latest stable).

### "Threads API: Invalid or expired access_token"
→ Meta tokens expire every 60 days. Refresh at https://developers.facebook.com/tools/explorer/

### Playwright timeout on Threads screenshot
→ Login cookies corrupted or expired. Delete `video_creation/data/cookie-threads.json` to force fresh login next run.

### "No eligible Threads posts found"
→ Configure `[threads.thread].min_replies = 5` (or lower). Ensure your Threads account has public posts with replies.

### Video dedup not working
→ Check `video_creation/data/videos.json` is writable. Ensure `check_done_by_id()` is called before fetching content.

---

## Testing Checklist

- [ ] Reddit mode: `platform = "reddit"` produces video to `results/{subreddit}/`
- [ ] Threads mode: `platform = "threads"` produces video to `results/threads/`
- [ ] Video dedup: Running same post_id twice skips second run
- [ ] Translation: `post_lang = "es"` translates filenames
- [ ] TTS providers: Test with different voice_choice values
- [ ] Background selection: Custom background video/audio works
- [ ] Story mode: storymode=true only uses thread_post, not comments
- [ ] Error handling: Invalid credentials show clear messages

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `main.py` | CLI entry; orchestrates pipeline via factory |
| `platforms/__init__.py` | Factory dispatch for multi-platform support |
| `platforms/threads/fetcher.py` | Threads Graph API client |
| `platforms/threads/screenshot.py` | Threads.net Playwright screenshotter |
| `video_creation/final_video.py` | FFmpeg composition; platform-aware output naming |
| `TTS/engine_wrapper.py` | TTS provider abstraction; post_lang fallback |
| `utils/settings.py` | Config loading & validation |
| `utils/videos.py` | Video dedup tracking |
| `utils/.config.template.toml` | Config schema |
| `requirements.txt` | Dependencies |

---

## Useful Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI
python3 main.py

# Run with specific post
python3 main.py <post_id>

# Run Flask GUI
python3 GUI.py

# Check syntax
python3 -m py_compile main.py platforms/threads/fetcher.py

# Format code
black main.py platforms/ utils/

# Lint
pylint main.py
```

---

## When You Get Stuck

1. **"What does this module do?"** → Check imports in `main.py` or docstrings
2. **"How do I add support for platform X?"** → See "Adding a New Platform" section above
3. **"Why is my config not being read?"** → Check `utils/settings.py:check_toml()` and `.config.template.toml` schema
4. **"Why isn't my TTS provider being called?"** → Check `TTS/engine_wrapper.py:make_voice()` and config `voice_choice`
5. **"How do I debug the Playwright screenshot?"** → Uncomment `page.pause()` in screenshot downloader, run headful browser

Good luck! 🚀

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **VideoMakerBot** (802 symbols, 1287 relationships, 32 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/VideoMakerBot/context` | Codebase overview, check index freshness |
| `gitnexus://repo/VideoMakerBot/clusters` | All functional areas |
| `gitnexus://repo/VideoMakerBot/processes` | All execution flows |
| `gitnexus://repo/VideoMakerBot/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
