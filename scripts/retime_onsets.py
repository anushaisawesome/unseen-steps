"""Start each line when its movement starts, on finished YouTube demos (no rewriting, no new voice).

YouTube demos have no audio to beat-match, and lines were placed after their movement, so they felt late and off the
beat. Dancers hit their movements on the music, so starting each line at its movement's onset lands it with the dancer.
Argon watches the few seconds around each line at 10 fps and gives the onset to a tenth of a second.

Usage: python scripts/retime_onsets.py data-keymoments.json track10 [ponyboy ...]
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "scripts"))
from google.genai import types  # noqa: E402
from director import client, video_part  # noqa: E402
from retry import with_retry  # noqa: E402

OUT = ROOT / "web/youtube-demo"
ONSET = {"type": "object", "properties": {"onset": {"type": "number", "nullable": True}}, "required": ["onset"]}


def onset(url: str, line: dict, start: float, end: float) -> float | None:
    a, b = max(start, line["at"] - 4), min(end, line["at"] + 1.5)
    r = with_retry(lambda: client().models.generate_content(
        model="gemini-4-argon", contents=[video_part(url, a, b, fps=10),
            f"This clip runs from {a:.1f} s to {b:.1f} s. At what exact time (seconds in the full video, to 0.1 s) does "
            f"the movement described here begin: \"{line['text']}\"? null if it isn't in the clip."],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=ONSET,
                                           thinking_config=types.ThinkingConfig(thinking_level="low"))))
    t = json.loads(r.text)["onset"]
    return t if t is not None and a - 0.5 <= t <= b else None


def retime(entry: dict) -> None:
    url = f"https://www.youtube.com/watch?v={entry['id']}"
    spoken = [l for l in entry["lines"] if l.get("audio")]
    with ThreadPoolExecutor(max_workers=8) as pool:
        onsets = list(pool.map(lambda l: onset(url, l, entry["start"], entry["end"]), spoken))
    for l, t in zip(spoken, onsets):
        if t is not None:
            l["was_at"], l["at"] = l["at"], round(t + 0.1, 2)
    finish = 0.0
    for l in sorted(spoken, key=lambda l: l["at"]):  # no talking over each other; a line can wait a beat at most
        if l["at"] < finish + 0.15:
            if finish + 0.15 - l["at"] > 0.6:
                l["status"], l["audio"] = "no room", None
                continue
            l["at"] = round(finish + 0.15, 2)
        finish = l["at"] + l["seconds"]
    entry["lines"].sort(key=lambda l: l["at"])
    for l in spoken:
        print(f"  {l.get('was_at', l['at']):5.1f}s -> {l['at']:5.1f}s {'' if l.get('audio') else '[no room] '}{l['text']}")


def main():
    path, keys = OUT / sys.argv[1], set(sys.argv[2:])
    client()  # create the client before the threads (lazily created clients race and get closed)
    data = json.loads(path.read_text())
    for entry in data:
        if entry["key"] in keys:
            print(entry["key"])
            retime(entry)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    path.with_suffix(".js").write_text("window.DEMOS = " + json.dumps(data, ensure_ascii=False) + ";\n")


if __name__ == "__main__":
    main()
