"""Turn a checked line into spoken audio with Gemini text-to-speech.

Usage:
    python server/speech.py "The couple sweeps to the left." out.wav
"""

import sys
import wave
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL = "gemini-3.8-flash-tts"
VOICE = "Kore"
RATE = 24000  # the model returns 16-bit mono PCM at 24 kHz

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def speak(line: str, path: Path) -> Path:
    """Say the line in a calm describer's voice and save it as a WAV file."""
    response = client().models.generate_content(
        model=MODEL,
        contents=line,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
        ),
    )
    pcm = response.candidates[0].content.parts[0].inline_data.data
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(pcm)
    return path


if __name__ == "__main__":
    print(speak(sys.argv[1], Path(sys.argv[2])))
