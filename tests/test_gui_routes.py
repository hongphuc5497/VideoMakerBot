from unittest.mock import MagicMock, patch

import GUI
from GUI import app


def test_background_add_handles_missing_form_fields():
    app.testing = False

    response = app.test_client().post("/background/add", data={})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/backgrounds")


def test_background_add_passes_empty_defaults_for_missing_optional_fields():
    app.testing = True

    with patch("GUI.gui.add_background") as add_background:
        response = app.test_client().post(
            "/background/add",
            data={"youtube_uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

    assert response.status_code == 302
    add_background.assert_called_once_with(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "",
        "",
        "",
    )


def test_settings_get_uses_template_defaults_for_partial_config():
    app.testing = True
    fake_path = MagicMock()
    fake_path.read_text.return_value = ""

    with patch("GUI.Path", MagicMock(return_value=fake_path)):
        response = app.test_client().get("/settings")

    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '"settings.tts.voice_choice": "Supertonic"' in body
    assert 'name="settings.tts.supertonic_voice"' in body


def test_public_demo_mode_blocks_mutating_routes(monkeypatch):
    app.testing = True
    monkeypatch.setattr(GUI, "PUBLIC_DEMO_MODE", True)
    client = app.test_client()

    assert client.post("/background/add", data={}).status_code == 403
    assert client.post("/background/delete", data={}).status_code == 403
    assert client.post("/settings", data={}).status_code == 403
    assert client.post("/videos/delete", json={"ids": ["abc"]}).status_code == 403
    assert client.post("/create", json={}).status_code == 403
