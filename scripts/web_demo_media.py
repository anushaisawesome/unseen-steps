"""Export a killtest run into the static demo site (web/): video, narration stem, captions, line data.

    python scripts/web_demo_media.py clips/ballet.mp4 data/killtest/ballet-script-3d.json

Writes web/media/<stem>.mp4 (picture + music), <stem>-narration.m4a (narration only, so the page can set its
volume separately), <stem>.vtt (the narration as captions), <stem>-reveal.mp4 (skeleton, captions and
narration burned in), <stem>-poster.jpg, and web/data/<stem>.json (lines, rejected drafts, beats, phrases).
"""

import json
import subprocess
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from music import load_audio, map_song  # noqa: E402

clip, run = Path(sys.argv[1]), Path(sys.argv[2])
stem = clip.stem
media, data = ROOT / "web/media", ROOT / "web/data"
media.mkdir(parents=True, exist_ok=True)
data.mkdir(parents=True, exist_ok=True)
results = json.loads(run.read_text(encoding="utf-8"))
SECONDS = 30  # the pipeline only analyses the first 30 s of every video


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


ffmpeg("-i", str(clip), "-t", str(SECONDS), "-vf", "scale=-2:720", "-c:v", "libx264", "-crf", "26",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(media / f"{stem}.mp4"))
ffmpeg("-ss", "13.8", "-i", str(clip), "-frames:v", "1", "-vf", "scale=-2:720", "-q:v", "4",
       str(media / f"{stem}-poster.jpg"))
annotated = run.with_name(run.stem + "-annotated.mp4")
ffmpeg("-i", str(annotated), "-vf", "scale=-2:720", "-c:v", "libx264", "-crf", "27", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(media / f"{stem}-reveal.mp4"))

# Narration stem: each spoken line placed at its time over silence, the clip's length.
spoken = [r for r in results if r.get("speech")]
cap = cv2.VideoCapture(str(media / f"{stem}.mp4"))
length = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
cap.release()
inputs, chains = [], []
for n, r in enumerate(spoken):
    inputs += ["-i", r["speech"]["path"]]
    ms = int(r["speech"]["at"] * 1000)
    chains.append(f"[{n}:a]aresample=48000,adelay={ms}|{ms}[a{n}]")
mix = "".join(f"[a{n}]" for n in range(len(spoken)))
ffmpeg(*inputs, "-filter_complex", ";".join(chains) + f";{mix}amix=inputs={len(spoken)}:normalize=0,"
       f"apad=whole_dur={length:.2f}[out]", "-map", "[out]", "-ac", "2", "-c:a", "aac", "-b:a", "96k",
       str(media / f"{stem}-narration.m4a"))


def stamp(t):
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:06.3f}"


cues = ["WEBVTT", ""]
for n, r in enumerate(spoken):
    sp = r["speech"]
    cues += [str(n + 1), f"{stamp(sp['at'])} --> {stamp(sp['at'] + sp['seconds'])}", r.get("line_en") or r["line"], ""]
(media / f"{stem}.vtt").write_text("\n".join(cues), encoding="utf-8")

song = map_song(load_audio(str(clip)), bars_per_phrase=2, speech_seconds=3.0, earliest=True)
lines = []
for r in results:
    sp = r.get("speech")
    lines.append({
        "text": r.get("line_en") or r.get("line"),
        "at": sp["at"] if sp else None, "seconds": sp["seconds"] if sp else None,
        "moment": r["moment"], "pace": r.get("pace"), "delivery": r.get("delivery"),
        "rejected": [{"draft": a["draft"], "reason": a["reason"].split("; measured in 3D")[0]}
                     for a in r["attempts"] if not a["passed"]],
        "measured": r["features"].get("timeline_3d", []),
    })
(data / f"{stem}.json").write_text(json.dumps({
    "clip": stem, "duration": round(length, 2), "bpm": song["bpm"], "beats_per_bar": song["beats_per_bar"],
    "beats": [round(b, 3) for b in song["beats"] if b < length],
    "phrases": [[round(a, 2), round(b, 2)] for a, b in song["phrases"] if a < length],
    "lines": lines,
}, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"web/media/{stem}*, web/data/{stem}.json: {len(spoken)} spoken lines, {len(song['beats'])} beats")
