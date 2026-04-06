# AGENT.md — Guidance for Agents & AI Working on VideoMakerBot

This document guides **agents, bots, and AI assistants** on how to work effectively with the VideoMakerBot codebase.

---

## Quick Start for Agents

### Core Principle
**VideoMakerBot uses a platform-agnostic factory pattern.** Always respect the abstraction:
- Don't import platform-specific modules (reddit/, threads/) directly
- Always use `platforms/__init__.py` factory functions
- Keep platform-specific logic in `platforms/{platform}/`

### The "Do This" Checklist
1. ✅ Read existing CLAUDE.md for architecture context
2. ✅ Use factory: `from platforms import get_content_object, get_screenshot_fn`
3. ✅ Return standard `content_object` dict from all fetchers
4. ✅ Test both Reddit and Threads modes before declaring completion
5. ✅ Use config fallback chains for cross-platform keys
6. ✅ Document platform-specific logic in docstrings

### The "Don't Do This" List
1. ❌ Import `reddit.subreddit` directly in main.py or generic modules
2. ❌ Hardcode subreddit/platform names in core video pipeline
3. ❌ Add platform-specific selectors outside `platforms/{platform}/`
4. ❌ Assume config keys exist without `.get()` and fallbacks
5. ❌ Modify screenshot_downloader.py for non-Reddit platforms

---

## Understanding the Codebase Structure

### Entry Point
**`main.py`** — Single CLI entry point using platform factory
- Calls `get_content_object(POST_ID)` from factory
- Calls `get_screenshot_fn()` from factory
- Everything else is platform-agnostic

### Platform Layer (`platforms/`)
- **`__init__.py`** — Factory dispatch functions (add new platforms here)
- **`threads/fetcher.py`** — Threads Graph API client (returns standard dict)
- **`threads/screenshot.py`** — Threads.net Playwright screenshotter

### Legacy Platform (`reddit/`)
- **`subreddit.py`** — PRAW API client (returns standard dict)
- No changes needed; called via factory

### Video Pipeline (`video_creation/`)
- **`final_video.py`** — FFmpeg composition (platform-aware output folder only)
- **`screenshot_downloader.py`** — Reddit Playwright screenshotter (not called for Threads)
- **`voices.py`** — TTS orchestration (platform-agnostic)
- **`background.py`** — Video/audio download (platform-agnostic)

### TTS Layer (`TTS/`)
- **`engine_wrapper.py`** — Provider abstraction (handles `post_lang` fallback)
- **`*.py`** — Individual provider implementations (elevenlabs, aws_polly, etc.)

### Config & Utils (`utils/`)
- **`settings.py`** — TOML config loading & validation
- **`videos.py`** — Dedup tracking (`check_done()` + `check_done_by_id()`)
- **`.config.template.toml`** — Config schema with `[settings]`, `[reddit.*]`, `[threads.*]`, `[ai]`

---

## How to Approach Common Tasks

### Adding a New Social Platform (e.g., X/Twitter)

**Steps:**
1. Create `platforms/twitter/fetcher.py`:
   ```python
   def get_twitter_content(POST_ID=None) -> dict:
       """Fetch post + replies, return standard content_object."""
       # Implement API fetching logic here
       return {
           "thread_id": ...,
           "thread_category": "twitter",  # NEW: generic field for output folder
           "thread_title": ...,
           "thread_url": ...,
           "comments": [...]
       }
   ```

2. Create `platforms/twitter/screenshot.py`:
   ```python
   def get_screenshots_of_twitter_posts(content_object: dict, screenshot_num: int):
       """Use Playwright to screenshot X/Twitter posts."""
       # Implement Playwright logic here
   ```

3. Update `platforms/__init__.py`:
   ```python
   elif platform == "twitter":
       from platforms.twitter.fetcher import get_twitter_content
       return get_twitter_content(POST_ID)
   ```

4. Add config section to `utils/.config.template.toml`:
   ```toml
   [twitter.creds]
   api_key = { ... }
   api_secret = { ... }

   [twitter.thread]
   post_id = { ... }
   ```

5. Update `main.py` helper:
   ```python
   elif platform == "twitter":
       return config.get("twitter", {}).get("thread", {}).get("post_id", "")
   ```

6. **Zero changes needed to:** TTS, backgrounds, video composition, utils.

**Verification:**
```bash
# Test Reddit (regression check)
sed -i 's/platform = "twitter"/platform = "reddit"/' config.toml
python3 main.py
# Verify results/{subreddit}/ output

# Test Twitter
sed -i 's/platform = "reddit"/platform = "twitter"/' config.toml
python3 main.py --post-id <twitter-id>
# Verify results/twitter/ output
```

---

### Modifying the Video Pipeline

**Scenario:** You need to change FFmpeg composition or add a new processing step.

**Approach:**
1. Check which data the modified code consumes (`content_object` dict)
2. Verify it works with both Reddit and Threads content structures
3. If platform-specific: move logic to `platforms/{platform}/`
4. If generic: keep in `video_creation/`
5. Test both modes before merging

**Example:** Adding video filters
```python
# In final_video.py (generic, works for all platforms)
def apply_filter(video_clip, filter_type):
    # No platform-specific logic here
    return video_clip.filter(...)

# Test:
# - Reddit mode produces filtered video
# - Threads mode produces filtered video
```

---

### Fixing a Bug in Config Handling

**Scenario:** `post_lang` is not being applied correctly.

**Debug Path:**
1. Check `utils/settings.py` — how is config loaded?
2. Check `TTS/engine_wrapper.py:182` — uses fallback chain:
   ```python
   lang = (settings.config["settings"].get("post_lang") or
           settings.config.get("reddit", {}).get("thread", {}).get("post_lang", ""))
   ```
3. Check `video_creation/final_video.py:78` — same fallback logic
4. If still broken: verify `utils/.config.template.toml` has the key defined
5. Test both platforms with `post_lang = "es"` in config

---

### Adding Support for a New TTS Provider

**Scenario:** User wants Whisper TTS support.

**Steps:**
1. Create `TTS/whisper_tts.py`:
   ```python
   class WhisperTTS:
       def make_voice(self, text):
           # Call Whisper API
           return audio_bytes
   ```

2. Update `TTS/engine_wrapper.py:make_voice()`:
   ```python
   elif voice_choice == "whisper":
       from TTS.whisper_tts import WhisperTTS
       return WhisperTTS().make_voice(text)
   ```

3. Add config to `utils/.config.template.toml`:
   ```toml
   [settings.tts]
   whisper_api_key = { optional = true, ... }
   ```

4. Test:
   ```bash
   # In config.toml:
   voice_choice = "whisper"
   # Run: python3 main.py
   ```

---

## Common Pitfalls & How to Avoid Them

### Pitfall 1: Platform-Specific Code in Generic Modules
**Problem:**
```python
# BAD: In video_creation/final_video.py
subreddit = settings.config["reddit"]["thread"]["subreddit"]
```
**Will break** when platform = "threads" (no reddit.thread.subreddit).

**Solution:**
```python
# GOOD:
platform = settings.config["settings"].get("platform", "reddit")
if platform == "reddit":
    category = settings.config["reddit"]["thread"]["subreddit"]
else:
    category = reddit_obj.get("thread_category", platform)
```

### Pitfall 2: Hardcoding Selectors in Platform-Agnostic Code
**Problem:**
```python
# BAD: In video_creation/voices.py
element = page.locator("#t1_{comment_id}")  # Reddit-only selector!
```
**Will fail** when running Threads mode (different DOM).

**Solution:**
- Keep all Playwright logic in `platforms/{platform}/screenshot.py`
- Never hardcode selectors in generic modules

### Pitfall 3: Forgetting to Test Both Modes
**Problem:** You change `final_video.py`, test with Reddit, declare done.
Threads mode breaks because you didn't test it.

**Solution:**
```bash
# Test both before committing:
sed -i 's/platform = "threads"/platform = "reddit"/' config.toml
python3 main.py
# Check results/{subreddit}/

sed -i 's/platform = "reddit"/platform = "threads"/' config.toml
python3 main.py --post-id <id>
# Check results/threads/
```

### Pitfall 4: Assuming Config Keys Exist
**Problem:**
```python
# BAD:
lang = settings.config["reddit"]["thread"]["post_lang"]
```
**Will crash** if key doesn't exist.

**Solution:**
```python
# GOOD:
lang = (settings.config["settings"].get("post_lang") or
        settings.config.get("reddit", {}).get("thread", {}).get("post_lang", ""))
```

---

## Code Review Checklist for Agents

Before marking work complete, verify:

- [ ] **No platform imports in main.py** — Uses factory only
- [ ] **Standard content_object dict** — All fetchers return same shape
- [ ] **Platform-specific logic isolated** — Only in `platforms/{platform}/`
- [ ] **Config fallback chains** — No hardcoded section names in generic code
- [ ] **Both modes tested** — Reddit AND Threads produce correct output
- [ ] **Docstrings updated** — New functions document platform assumptions
- [ ] **Error messages clear** — Include platform name + actionable guidance
- [ ] **Video dedup works** — No duplicate videos created

---

## Understanding Data Flow

### Happy Path: Fetch → TTS → Screenshot → Compose → Output

```
1. main.py:main()
   └─→ platforms/__init__.py:get_content_object()
       └─→ platforms/threads/fetcher.py:get_threads_content()
           └─→ Returns: {thread_id, thread_title, comments, ...}

2. video_creation/voices.py:save_text_to_mp3()
   └─→ TTS/engine_wrapper.py:process_text()
       └─→ TTS/engine_wrapper.py:make_voice()
           └─→ TTS/{provider}.py: {elevenlabs,tiktok,etc}
               └─→ Returns: audio_length, comment_count

3. platforms/__init__.py:get_screenshot_fn()
   └─→ platforms/threads/screenshot.py:get_screenshots_of_threads_posts()
       └─→ Uses Playwright on threads.net
           └─→ Saves: assets/temp/{thread_id}/png/{title,comment_0,etc}.png

4. video_creation/background.py
   └─→ download_background_video() & download_background_audio()
       └─→ Uses yt-dlp to fetch YouTube videos/audio
           └─→ Saves to: assets/temp/{thread_id}/{video,audio}

5. video_creation/final_video.py:make_final_video()
   └─→ Uses FFmpeg to compose everything
       └─→ Reads: audio files, screenshot PNGs, background video
           └─→ Writes: results/{thread_category}/{filename}.mp4

6. utils/videos.py:save_data()
   └─→ Records video in videos.json for dedup
```

### Config Flow

```
config.toml (user settings)
    ↓
utils/settings.py:check_toml()
    └─→ Validates against .config.template.toml schema
        └─→ Returns: settings.config (dict)

            Used by:
            ├─ main.py (platform selection)
            ├─ platforms/reddit/ (subreddit, etc.)
            ├─ platforms/threads/ (Graph API token, etc.)
            ├─ TTS/engine_wrapper.py (post_lang fallback)
            ├─ video_creation/ (theme, resolution, etc.)
            └─ utils/videos.py (dedup behavior)
```

---

## Deployment Notes

### Python Version
- **Minimum:** 3.10
- **Tested:** 3.10, 3.11, 3.12
- **Reason:** F-strings, type hints, modern async patterns

### Critical Dependencies
- **reddit platform:** praw 7.8.1 (requires Reddit OAuth app)
- **threads platform:** requests (for Graph API calls)
- **screenshots:** playwright 1.49.1 (requires browser installation: `playwright install`)
- **video:** moviepy 2.2.1, ffmpeg-python 0.2.0 (requires FFmpeg system binary)
- **tts:** varies per provider (elevenlabs, aws_polly, openai, etc.)

### Versions That Caused Issues
- **yt-dlp==2026.3.17** — Doesn't exist (use 2025.10.14 or latest stable)
- **playwright without browser install** — Will crash on first screenshot

---

## When to Escalate

### Escalate to User if:
- User needs new platform support (only they know requirements)
- Config changes affect backward compatibility
- Performance optimization needed (only user knows acceptable limits)
- Security concern (token handling, credential storage, etc.)

### Safe to Implement as Agent:
- Bug fixes within existing architecture
- Adding new TTS providers
- Extending config options for existing platforms
- Performance optimizations (caching, parallelization)
- New filter/processing features that work platform-agnostically
- Documentation & refactoring

---

## Final Guidance

**Golden Rule:** The factory pattern is your friend. When in doubt, check if your change breaks the abstraction. If it does, rethink it.

**Test Obsessively:** Always run both Reddit and Threads modes. The codebase is designed for multi-platform support, and it's easy to break one platform while fixing another.

**Document Platform Assumptions:** If your code works differently for Reddit vs Threads, say so explicitly in docstrings and comments.

**Ask Yourself:** "Would this work for X/Twitter?" If no, it probably belongs in `platforms/threads/`, not in generic code.

Good luck, and happy contributing! 🎥
