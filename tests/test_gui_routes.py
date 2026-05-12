from unittest.mock import patch

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
