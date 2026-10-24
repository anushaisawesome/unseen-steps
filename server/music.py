"""Map a song before the show: beats, phrases and the clean spaces to speak in.

Usage:
    python server/music.py <audio or video file> --name "Song" --style waltz --beats-per-bar 3
Writes data/songs/<slug>.json in the shared song format.
"""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np

SR = 22050
AUDIO_EXTS = {".wav", ".flac", ".ogg", ".mp3"}


def load_audio(path: str) -> np.ndarray:
    """Load mono audio, pulling the soundtrack out of video files with ffmpeg."""
    if Path(path).suffix.lower() in AUDIO_EXTS:
        y, _ = librosa.load(path, sr=SR, mono=True)
        return y
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(SR), tmp.name],
            check=True,
        )
        y, _ = librosa.load(tmp.name, sr=SR, mono=True)
    return y


def map_song(y: np.ndarray, beats_per_bar: int = 4, bars_per_phrase: int = 8,
             speech_seconds: float = 3.0, search_bars: int = 2, earliest: bool = False) -> dict:
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=SR)
    beats = librosa.frames_to_time(beat_frames, sr=SR)
    if len(beats) < 2:
        raise ValueError("Couldn't find a beat in this track")

    # Loudness and accent at each beat, used to place phrase starts and clean spaces.
    onset = librosa.onset.onset_strength(y=y, sr=SR)
    rms = librosa.feature.rms(y=y)[0]
    accent = onset[np.minimum(beat_frames, len(onset) - 1)]
    loudness = np.array([
        rms[a:b].mean() if b > a else rms[min(a, len(rms) - 1)]
        for a, b in zip(beat_frames, list(beat_frames[1:]) + [len(rms)])
    ])

    # Phrases start on strong downbeats: try every offset and keep the most accented one.
    phrase_beats = beats_per_bar * bars_per_phrase
    offset = max(range(phrase_beats), key=lambda o: accent[o::phrase_beats].mean())
    starts = list(range(offset, len(beats), phrase_beats))

    end_time = len(y) / SR
    phrases = [[float(beats[s]), float(beats[e]) if e < len(beats) else end_time]
               for s, e in zip(starts, starts[1:] + [len(beats)])]

    # Clean space after each phrase: the quietest stretch long enough for one spoken line,
    # starting in the first bars of the next phrase but never on its downbeat, which is
    # usually the loudest moment.
    beat_seconds = float(np.median(np.diff(beats)))
    window = max(1, int(np.ceil(speech_seconds / beat_seconds)))
    clean_spaces = []
    for nxt in starts[1:]:
        candidates = [nxt + k for k in range(1, search_bars * beats_per_bar)
                      if nxt + k + window < len(beats)]
        if not candidates:
            clean_spaces.append(None)
            continue
        quiet = {c: loudness[c:c + window].mean() for c in candidates}
        if earliest:  # the first gap that's no louder than average, so lines stay close to the movement
            typical = float(np.median(list(quiet.values())))
            best = next(c for c in candidates if quiet[c] <= typical)
        else:
            best = min(candidates, key=quiet.get)
        clean_spaces.append([float(beats[best]), float(beats[best + window])])
    clean_spaces.append(None)  # nothing to speak into after the last phrase

    return {
        "bpm": round(float(np.atleast_1d(tempo)[0]), 1),
        "beats_per_bar": beats_per_bar,
        "beats": [round(float(b), 3) for b in beats],
        "phrases": [[round(s, 3), round(e, 3)] for s, e in phrases],
        "clean_spaces": [[round(c[0], 3), round(c[1], 3)] if c else None for c in clean_spaces],
    }


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--name", required=True)
    parser.add_argument("--style", default="unknown")
    parser.add_argument("--beats-per-bar", type=int, default=4, help="3 for waltz, 4 for most styles")
    args = parser.parse_args()

    song = {"name": args.name, "style": args.style,
            **map_song(load_audio(args.path), beats_per_bar=args.beats_per_bar)}

    out = Path("data/songs") / f"{slugify(args.name)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(song, indent=2))

    print(f"{song['name']}: {song['bpm']} bpm, {len(song['phrases'])} phrases -> {out}")
    for i, (phrase, space) in enumerate(zip(song["phrases"], song["clean_spaces"])):
        speak = f"speak {space[0]:6.2f}-{space[1]:6.2f}s" if space else "no clean space"
        print(f"  phrase {i:2d}: {phrase[0]:6.2f}-{phrase[1]:6.2f}s  {speak}")


if __name__ == "__main__":
    main()
