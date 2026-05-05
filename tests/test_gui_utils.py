import json
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from utils import gui_utils

@pytest.fixture
def mock_background_json(tmp_path):
    bg_file = tmp_path / "background_videos.json"
    initial_data = {
        "__comment": "test",
        "minecraft": ["https://www.youtube.com/watch?v=n_Dv4JMiwK8", "parkour.mp4", "bbswitzer", "center"]
    }
    bg_file.write_text(json.dumps(initial_data))
    return bg_file

@pytest.fixture
def mock_template_toml(tmp_path):
    template_file = tmp_path / ".config.template.toml"
    template_content = """
[settings.background]
background_video = { optional = true, default = "minecraft", options = ["minecraft"] }
"""
    template_file.write_text(template_content)
    return template_file

@patch("utils.gui_utils.flash")
def test_delete_background(mock_flash, mock_background_json, mock_template_toml):
    # We need to patch the paths used in gui_utils
    with patch("utils.gui_utils.open", MagicMock(side_effect=lambda path, *args, **kwargs: open(mock_background_json if "background_videos.json" in str(path) else path, *args, **kwargs))), \
         patch("utils.gui_utils.Path", MagicMock(side_effect=lambda path: Path(mock_template_toml) if ".config.template.toml" in str(path) else Path(path))):
        
        gui_utils.delete_background("minecraft")
        
        # Verify background_videos.json
        with open(mock_background_json, "r") as f:
            data = json.load(f)
        assert "minecraft" not in data
        
        # Verify .config.template.toml
        import tomlkit
        template_data = tomlkit.loads(mock_template_toml.read_text())
        assert "minecraft" not in template_data["settings"]["background"]["background_video"]["options"]
        
        mock_flash.assert_called_with('Successfully removed "minecraft" background!')

@patch("utils.gui_utils.flash")
def test_add_background(mock_flash, mock_background_json, mock_template_toml):
    with patch("utils.gui_utils.open", MagicMock(side_effect=lambda path, *args, **kwargs: open(mock_background_json if "background_videos.json" in str(path) else path, *args, **kwargs))), \
         patch("utils.gui_utils.Path", MagicMock(side_effect=lambda path: Path(mock_template_toml) if ".config.template.toml" in str(path) else Path(path))):
        
        # Test adding a new background
        gui_utils.add_background(
            youtube_uri="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            filename="test_new",
            citation="Rick",
            position="center"
        )
        
        # Verify background_videos.json
        with open(mock_background_json, "r") as f:
            data = json.load(f)
        assert "test_new" in data
        assert data["test_new"][0] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        
        # Verify .config.template.toml
        import tomlkit
        template_data = tomlkit.loads(mock_template_toml.read_text())
        assert "test_new" in template_data["settings"]["background"]["background_video"]["options"]
        
        mock_flash.assert_called_with('Added "Rick-test_new.mp4" as a new background video!')
