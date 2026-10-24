# Copied from server/speech.py by scripts/web_sync_server.py: edit the original.
"""Turn a checked line into spoken audio with Gemini text-to-speech.

Delivery: an optional director's note sets the tone ("hushed, tender" or "punchy, explosive"). The TTS model
sometimes reads such notes aloud, so every clip is transcribed and compared with the line, and regenerated
plainly if extra words crept in. Speed is set by time-stretching the audio (pitch kept) to fit the time the
line has before the next one, rather than trusting the model's pace.

Usage:
    python server/speech.py "The couple sweeps to the left." out.wav
"""

import io
import re
import subprocess
import sys
import wave
from pathlib import Path

from google import genai
from google.genai import types

try:
    from .retry import with_retry
except ImportError:
    from retry import with_retry
try:
    from .settings import gemini_api_key
except ImportError:  # Running as ``python server/speech.py``.
    from settings import gemini_api_key

MODEL = "gemini-3.8-flash-tts"
VOICE = "Kore"
RATE = 24000  # the model returns 16-bit mono PCM at 24 kHz

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=gemini_api_key())
    return _client


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def _faithful(audio: bytes, mime: str, line: str) -> bool:
    """True if the clip says the line and nothing else (no director's note read aloud)."""
    heard = with_retry(lambda: client().models.generate_content(
        model="gemini-3.8-flash",
        contents=[types.Part.from_bytes(data=audio, mime_type=mime), "Transcribe exactly what is spoken. Nothing else."],
    )).text
    return len(_words(heard)) <= len(_words(line)) + 2


def speak(line: str, path: Path, delivery: str | None = None, max_seconds: float | None = None) -> Path:
    """Say the line (in the delivery's tone, if given), fit it into max_seconds, and save it as a WAV file."""
    if delivery:
        _synthesise(f"# DIRECTOR'S NOTES\n{delivery}\n\n# TRANSCRIPT\n{line}", path)
        if not _faithful(path.read_bytes(), "audio/wav", line):
            _synthesise(line, path)
    else:
        _synthesise(line, path)
    if max_seconds:
        with wave.open(str(path)) as f:
            seconds = f.getnframes() / f.getframerate()
        if seconds > max_seconds:  # speed up to fit, up to 1.35x (beyond that it stops sounding natural)
            factor = min(1.35, seconds / max_seconds)
            stretched = path.with_suffix(".fit.wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-filter:a", f"atempo={factor:.3f}",
                            str(stretched)], check=True)
            stretched.replace(path)
    return path


def _synthesise(contents: str, path: Path) -> Path:
    response = with_retry(lambda: client().models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
        ),
    ))
    audio = response.candidates[0].content.parts[0].inline_data
    if audio.mime_type == "audio/wav":
        # Already a complete WAV (header plus a metadata chunk at the end): read the sound
        # out of it so the metadata isn't played as noise.
        with wave.open(io.BytesIO(audio.data)) as src:
            params, frames = src.getparams(), src.readframes(src.getnframes())
        with wave.open(str(path), "wb") as f:
            f.setparams(params)
            f.writeframes(frames)
    else:  # raw 16-bit mono PCM
        with wave.open(str(path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(RATE)
            f.writeframes(audio.data)
    return path


if __name__ == "__main__":
    print(speak(sys.argv[1], Path(sys.argv[2])))
