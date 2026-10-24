"""Turn a checked line into spoken audio with Gemini text-to-speech.

Delivery: an optional director's note sets the tone ("hushed, tender" or "punchy, explosive"). The TTS model
sometimes reads such notes aloud, and sometimes swaps or drops words ("fold" came out as "full"), so Gemini Flash
listens to every clip and compares it with the caption; it's re-recorded (up to three takes, the last plain) until
they match. Speed is set by time-stretching the audio (pitch kept) to fit the time the
line has before the next one, rather than trusting the model's pace.

Usage:
    python server/speech.py "The couple sweeps to the left." out.wav
"""

import io
import json
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


MATCH = {"type": "object", "properties": {"match": {"type": "boolean"}, "heard": {"type": "string"}},
         "required": ["match", "heard"]}


def _faithful(audio: bytes, mime: str, line: str) -> tuple[bool, str]:
    """Does the clip say exactly the line (caption), with nothing added, dropped or swapped? Dance terms in
    French count as matching if they're recognisably said."""
    response = with_retry(lambda: client().models.generate_content(
        model="gemini-3.8-flash",
        contents=[types.Part.from_bytes(data=audio, mime_type=mime),
                  f"The caption for this clip is: {line!r}\nListen and write down what is actually said (heard). "
                  "match is true if the speech says the caption's words in order. It is false only if a word is added, "
                  "dropped or replaced by a different word, or something else is read out (like a stage direction). "
                  "Plural endings, 'a'/'the', punctuation and the pronunciation of dance terms don't count."],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=MATCH,
                                           thinking_config=types.ThinkingConfig(thinking_level="low")),
    ))
    result = json.loads(response.text)
    return result["match"], result["heard"]


def speak(line: str, path: Path, delivery: str | None = None, max_seconds: float | None = None) -> Path:
    """Say the line (in the delivery's tone, if given), check the voice said exactly the caption, fit it into
    max_seconds, and save it as a WAV file. Up to three takes: with the tone note twice, then plain."""
    takes = [f"# DIRECTOR'S NOTES\n{delivery}\n\n# TRANSCRIPT\n{line}"] * 2 if delivery else [line]
    takes.append(line)
    for n, contents in enumerate(takes):
        _synthesise(contents, path)
        ok, heard = _faithful(path.read_bytes(), "audio/wav", line)
        if ok:
            break
        print(f"   voice take {n + 1} said {heard!r} instead of {line!r}")
    else:
        print(f"   WARNING: voice still doesn't match the caption after {len(takes)} takes: {line!r}")
    _tighten(path)
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


def _tighten(path: Path) -> None:
    """Trim the silence the model leaves at both ends and shorten the long pauses it puts at commas, which make
    lines drag (a third of a typical clip is silence)."""
    tight = path.with_suffix(".tight.wav")
    trim = "silenceremove=start_periods=1:start_threshold=-35dB"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-af",
                    f"{trim},areverse,{trim},areverse,"
                    "silenceremove=stop_periods=-1:stop_duration=0.1:stop_threshold=-35dB:detection=rms",
                    str(tight)], check=True)
    tight.replace(path)


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
