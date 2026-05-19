import random
import subprocess
import tempfile
from pathlib import Path

from supertonic import TTS

from utils import settings


class SupertonicTTS:
    def __init__(self):
        self.max_chars = 300
        self.tts = TTS(auto_download=True)

    def run(self, text, filepath, random_voice: bool = False):
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        tts_settings = settings.config["settings"].get("tts", {})
        voice_style = self._voice_style(tts_settings, random_voice)

        wav, _duration = self.tts.synthesize(
            text,
            voice_style=voice_style,
            lang=tts_settings.get("supertonic_lang", "na"),
            total_steps=int(tts_settings.get("supertonic_steps", 8)),
            speed=float(tts_settings.get("supertonic_speed", 1.05)),
            max_chunk_length=self.max_chars,
            verbose=False,
        )

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            wav_path = Path(temp_wav.name)

        try:
            self.tts.save_audio(wav, str(wav_path))
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(wav_path),
                    str(output_path),
                ],
                check=True,
            )
        finally:
            wav_path.unlink(missing_ok=True)

    def randomvoice(self):
        return random.choice(list(self.tts.voice_style_names))

    def _voice_style(self, tts_settings: dict, random_voice: bool):
        custom_voice_path = str(tts_settings.get("supertonic_custom_voice_path", "")).strip()
        if custom_voice_path:
            return self.tts.get_voice_style_from_path(custom_voice_path)

        voice_name = self.randomvoice() if random_voice else tts_settings.get("supertonic_voice", "M1")
        return self.tts.get_voice_style(voice_name=str(voice_name))