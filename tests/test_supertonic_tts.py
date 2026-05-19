from pathlib import Path

from utils import settings


class FakeSupertonicEngine:
    voice_style_names = ["M1", "F1"]

    def __init__(self, auto_download=True):
        self.auto_download = auto_download

    def get_voice_style(self, voice_name):
        return {"voice_name": voice_name}

    def get_voice_style_from_path(self, path):
        return {"path": path}

    def synthesize(self, text, **kwargs):
        return b"wav-data", 1.0

    def save_audio(self, wav, path):
        Path(path).write_bytes(wav)


def test_supertonic_tts_converts_wav_to_mp3(monkeypatch, tmp_path):
    import TTS.supertonic_tts as supertonic_module

    run_calls = []

    def fake_run(command, check):
        run_calls.append((command, check))
        Path(command[-1]).write_bytes(b"mp3-data")

    settings.config = {
        "settings": {
            "tts": {
                "supertonic_voice": "M1",
                "supertonic_lang": "na",
                "supertonic_steps": 8,
                "supertonic_speed": 1.05,
                "supertonic_custom_voice_path": "",
            }
        }
    }
    monkeypatch.setattr(supertonic_module, "TTS", FakeSupertonicEngine)
    monkeypatch.setattr(supertonic_module.subprocess, "run", fake_run)

    output_path = tmp_path / "voice.mp3"
    supertonic_module.SupertonicTTS().run("hello", str(output_path))

    assert output_path.read_bytes() == b"mp3-data"
    command, check = run_calls[0]
    assert command[:5] == ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    assert command[-1] == str(output_path)
    assert check is True