from utils.settings import apply_template_defaults


def test_apply_template_defaults_fills_missing_values_without_overwriting(tmp_path):
    template = tmp_path / "template.toml"
    template.write_text(
        """
[settings]
platform = { optional = false, default = "reddit" }

[settings.tts]
no_emojis = { optional = false, default = false, type = "bool" }

[threads.creds]
access_token = { optional = false }
username = { optional = true }

[threads.thread]
min_replies = { optional = false, default = 5, type = "int" }
search_queries = { optional = true, default = "news,politics,trending" }
"""
    )
    config = {
        "settings": {"platform": "threads"},
        "threads": {"creds": {"username": "configured-user"}},
    }

    result = apply_template_defaults(config, str(template))

    assert result["settings"]["platform"] == "threads"
    assert result["settings"]["tts"]["no_emojis"] is False
    assert result["threads"]["thread"]["min_replies"] == 5
    assert result["threads"]["thread"]["search_queries"] == "news,politics,trending"
    assert result["threads"]["creds"]["username"] == "configured-user"
    assert "access_token" not in result["threads"]["creds"]


def test_real_template_defaults_to_supertonic_tts():
    result = apply_template_defaults({"settings": {}})

    assert result["settings"]["tts"]["voice_choice"] == "Supertonic"
    assert result["settings"]["tts"]["supertonic_voice"] == "M1"
    assert result["settings"]["tts"]["supertonic_lang"] == "na"