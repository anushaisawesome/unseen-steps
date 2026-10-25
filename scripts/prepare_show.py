"""A studio prepares a show: Argon writes the show notes from the rehearsal video, and they're stored in MongoDB Atlas
(collection `shows`) with the song's gaps, ready for the live narration (`scripts/live.py --show "<name>"`).

Usage:
    python scripts/prepare_show.py --name "Spring showcase: Andrii, waltz" --rehearsal clips/andrii720.mp4 \
        --song clips/andrii720.mp4 --style waltz --beats-per-bar 3 [--studio "KCL Dance"]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from db import db  # noqa: E402
from music import load_audio, map_song  # noqa: E402
from show_notes import prepare  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--rehearsal", required=True)
    parser.add_argument("--song", required=True)
    parser.add_argument("--style")
    parser.add_argument("--studio", default="")
    parser.add_argument("--beats-per-bar", type=int, default=4)
    args = parser.parse_args()

    plan, moments, notes = prepare(args.rehearsal, args.style)
    song = map_song(load_audio(args.song), beats_per_bar=args.beats_per_bar, bars_per_phrase=2,
                    speech_seconds=2.5, earliest=True)
    doc = {"name": args.name, "studio": args.studio, "style": plan["style"]["name"], "song": Path(args.song).name,
           "bpm": song["bpm"], "gaps": [g for g in song["clean_spaces"] if g], "plan": plan,
           "key_moments": [list(m) for m in moments], "show_notes": notes,
           "updated": datetime.now(timezone.utc)}
    db()["shows"].update_one({"name": args.name}, {"$set": doc}, upsert=True)
    print(f"stored in Atlas: {args.name} ({doc['style']}, {len(moments)} key moments, {len(doc['gaps'])} gaps)")


if __name__ == "__main__":
    main()
