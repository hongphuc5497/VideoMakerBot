import io
import json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Used "tomlkit" instead of "toml" because it doesn't change formatting on "dump"
import tomlkit
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)

import utils.gui_utils as gui
from utils.docker_bootstrap import ensure_runtime_state

ensure_runtime_state()

# Set the hostname and port
HOST = os.environ.get("GUI_HOST", "0.0.0.0")
PORT = int(os.environ.get("GUI_PORT", "4000"))
OPEN_BROWSER = os.environ.get("GUI_OPEN_BROWSER", "1").lower() in {"1", "true", "yes", "on"}
BROWSER_URL = os.environ.get("GUI_BROWSER_URL", f"http://localhost:{PORT}")

# Configure application
app = Flask(__name__, template_folder="GUI")

# Configure secret key only to use 'flash'
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Display index.html
@app.route("/")
def index():
    return render_template("index.html", file="videos.json")


@app.route("/backgrounds", methods=["GET"])
def backgrounds():
    return render_template("backgrounds.html", file="backgrounds.json")


@app.route("/background/add", methods=["POST"])
def background_add():
    # Get form values
    youtube_uri = request.form.get("youtube_uri").strip()
    filename = request.form.get("filename").strip()
    citation = request.form.get("citation").strip()
    position = request.form.get("position").strip()

    gui.add_background(youtube_uri, filename, citation, position)

    return redirect(url_for("backgrounds"))


@app.route("/background/delete", methods=["POST"])
def background_delete():
    key = request.form.get("background-key")
    gui.delete_background(key)

    return redirect(url_for("backgrounds"))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    config_load = tomlkit.loads(Path("config.toml").read_text())
    config = gui.get_config(config_load)

    # Get checks for all values
    checks = gui.get_checks()

    if request.method == "POST":
        # Get data from form as dict
        data = request.form.to_dict()

        # Change settings
        config = gui.modify_settings(data, config_load, checks)

    return render_template("settings.html", file="config.toml", data=config, checks=checks)


# Make videos.json accessible
@app.route("/videos.json")
def videos_json():
    return send_from_directory("video_creation/data", "videos.json")


# Make backgrounds.json accessible
@app.route("/backgrounds.json")
def backgrounds_json():
    return send_from_directory("utils", "background_videos.json")


# Make videos in results folder accessible
@app.route("/results/<path:name>")
def results(name):
    as_attachment = request.args.get("download", "0").lower() in {"1", "true", "yes"}
    return send_from_directory("results", name, as_attachment=as_attachment)


# Serve a video by its videos.json id (handles filenames with unsafe chars like newlines)
@app.route("/video/<video_id>")
def video_by_id(video_id):
    try:
        with open("video_creation/data/videos.json", "r", encoding="utf-8") as f:
            videos = json.load(f)
    except (OSError, json.JSONDecodeError):
        abort(404)

    entry = next((v for v in videos if v.get("id") == video_id), None)
    if not entry:
        abort(404)

    subreddit = entry.get("subreddit", "")
    filename = entry.get("filename", "")
    file_path = (Path("results") / subreddit / filename).resolve()
    results_root = Path("results").resolve()

    # Prevent path traversal: ensure resolved file is inside results/
    try:
        file_path.relative_to(results_root)
    except ValueError:
        abort(404)

    if not file_path.is_file():
        abort(404)

    as_attachment = request.args.get("download", "0").lower() in {"1", "true", "yes"}
    safe_name = filename.replace("\n", " ").replace("\r", " ").strip() or f"{video_id}.mp4"
    return send_file(file_path, as_attachment=as_attachment, download_name=safe_name)


# Delete one or more videos by ID
@app.route("/videos/delete", methods=["POST"])
def video_delete():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    if not ids or not isinstance(ids, list):
        return jsonify({"error": "No IDs provided"}), 400
    deleted = gui.delete_videos(ids)
    return jsonify({"deleted": deleted})


# Make voices samples in voices folder accessible
@app.route("/voices/<path:name>")
def voices(name):
    return send_from_directory("GUI/voices", name, as_attachment=True)


# --- Pipeline state (shared across thread + HTTP) ---
pipeline_lock = threading.Lock()
pipeline_state: dict = {
    "running": False,
    "stage": "",
    "error": None,
    "result": None,  # {"title": ..., "file": ..., "url": ...}
    "log": [],       # Last N status messages
    "scraper_events": [],  # Structured scraper events for visualization
}


def _event_to_summary(event_type, data):
    """Convert a structured scraper event to a human-readable log line."""
    data = data or {}
    summaries = {
        "browser_launch": lambda d: "Launching browser...",
        "login": lambda d: d.get("message", "Login event"),
        "feed_scroll": lambda d: f"Scrolled: {d.get('new_posts', 0)} new, {d.get('total_posts', 0)} total",
        "post_discovered": lambda d: f"Post by {d.get('username', '?')}: {d.get('body', '')[:45]}",
        "search_query": lambda d: f"Search '{d.get('query', '?')}': {d.get('posts_found', 0)} posts",
        "filter_results": lambda d: f"Filtered {d.get('before', 0)} -> {d.get('after', 0)} candidates",
        "visiting_post": lambda d: f"Trying post {d.get('post_id', '')[:8]}...",
        "replies_found": lambda d: f"Got {d.get('count', 0)} replies (need {d.get('min_required', '?')})",
        "post_selected": lambda d: f"Selected: {d.get('title', '')[:55]}",
        "general": lambda d: d.get("message", ""),
    }
    fn = summaries.get(event_type)
    return fn(data) if fn else None


def _run_pipeline(search_queries=None):
    """Run the video creation pipeline in a background thread."""
    import toml
    from utils import console as uconsole
    from utils import settings

    with pipeline_lock:
        pipeline_state["running"] = True
        pipeline_state["stage"] = "configuring"
        pipeline_state["error"] = None
        pipeline_state["result"] = None
        pipeline_state["log"] = []
        pipeline_state["scraper_events"] = []

    try:
        # Load config
        settings.config = toml.load("config.toml")

        # Apply search_queries override if provided from UI
        if search_queries:
            settings.config.setdefault("threads", {}).setdefault("thread", {})["search_queries"] = search_queries

        # Set up progress callback with structured event support
        def on_progress(stage=None, event=None, data=None):
            with pipeline_lock:
                if stage:
                    pipeline_state["stage"] = stage
                    pipeline_state["log"].append(stage)
                    if len(pipeline_state["log"]) > 20:
                        pipeline_state["log"] = pipeline_state["log"][-20:]
                if event:
                    entry = {"type": event, "data": data or {}, "ts": time.time()}
                    pipeline_state["scraper_events"].append(entry)
                    if len(pipeline_state["scraper_events"]) > 100:
                        pipeline_state["scraper_events"] = pipeline_state["scraper_events"][-100:]
                    summary = _event_to_summary(event, data)
                    if summary:
                        pipeline_state["log"].append(summary)
                        if len(pipeline_state["log"]) > 20:
                            pipeline_state["log"] = pipeline_state["log"][-20:]

        uconsole.set_progress_callback(on_progress)

        from main import main as run_pipeline
        run_pipeline()

        with pipeline_lock:
            pipeline_state["stage"] = "done"
            pipeline_state["result"] = {"message": "Video created successfully! Check the home page."}

    except Exception as e:
        with pipeline_lock:
            pipeline_state["stage"] = "error"
            pipeline_state["error"] = str(e)[:500].encode("ascii", errors="replace").decode("ascii")
    finally:
        with pipeline_lock:
            pipeline_state["running"] = False
        uconsole.set_progress_callback(None)


@app.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        if pipeline_state["running"]:
            return jsonify({"status": "already_running"})
        data = request.get_json(silent=True) or {}
        search_queries = data.get("search_queries") or None
        thread = threading.Thread(
            target=_run_pipeline,
            kwargs={"search_queries": search_queries},
            daemon=True,
        )
        thread.start()
        return jsonify({"status": "started"})
    # Load current config default for pre-filling the keywords input
    cfg = tomlkit.loads(Path("config.toml").read_text())
    default_queries = cfg.get("threads", {}).get("thread", {}).get("search_queries", "")
    return render_template("create.html", state=pipeline_state, default_search_queries=default_queries)


@app.route("/create/status")
def create_status():
    with pipeline_lock:
        state_copy = dict(pipeline_state)
    return jsonify(state_copy)


# Run browser and start the app
if __name__ == "__main__":
    if OPEN_BROWSER:
        webbrowser.open(BROWSER_URL, new=2)
        print("Website opened in new tab. Refresh if it didn't load.")
    app.run(host=HOST, port=PORT)
