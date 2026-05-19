from pathlib import Path

from TTS.TikTok import TikTokTTSException
from TTS.engine_wrapper import TTSEngine
from utils import settings


class FailingTikTok:
    max_chars = 5000

    def run(self, text, filepath, random_voice=False):
        raise TikTokTTSException(1, "failed")


class FakeGTTS:
    max_chars = 5000

    def run(self, text, filepath):
        Path(filepath).write_text(text)


class FakeAudioFileClip:
    duration = 1.0

    def __init__(self, path):
        self.path = path

    def close(self):
        pass


def test_tiktok_fallback_uses_googletranslate_not_pyttsx(monkeypatch, tmp_path):
    import TTS.engine_wrapper as engine_wrapper

    settings.config = {
        "settings": {
            "tts": {"voice_choice": "tiktok", "random_voice": False},
        }
    }
    reddit_object = {"thread_id": "abc", "thread_title": "title", "comments": []}
    monkeypatch.setattr(engine_wrapper, "GTTS", FakeGTTS)
    monkeypatch.setattr(engine_wrapper, "AudioFileClip", FakeAudioFileClip)

    engine = TTSEngine(FailingTikTok, reddit_object, path=f"{tmp_path}/")
    Path(engine.path).mkdir(parents=True)

    engine.call_tts("title", "hello")

    assert settings.config["settings"]["tts"]["voice_choice"] == "googletranslate"
    assert Path(engine.path, "title.mp3").read_text() == "hello"