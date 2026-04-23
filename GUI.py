import os
import webbrowser
from pathlib import Path

# Used "tomlkit" instead of "toml" because it doesn't change formatting on "dump"
import tomlkit
from flask import (
    Flask,
    redirect,
    render_template,
    request,
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
    return send_from_directory("utils", "backgrounds.json")


# Make videos in results folder accessible
@app.route("/results/<path:name>")
def results(name):
    return send_from_directory("results", name, as_attachment=True)


# Make voices samples in voices folder accessible
@app.route("/voices/<path:name>")
def voices(name):
    return send_from_directory("GUI/voices", name, as_attachment=True)


# Run browser and start the app
if __name__ == "__main__":
    if OPEN_BROWSER:
        webbrowser.open(BROWSER_URL, new=2)
        print("Website opened in new tab. Refresh if it didn't load.")
    app.run(host=HOST, port=PORT)
