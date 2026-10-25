"""Let a studio (or a describer working with it) read and correct a show's notes before the night.

    python scripts/edit_show.py "Demo: Andrii, waltz"

Opens the show notes and the rehearsal script from MongoDB Atlas in a text editor ($EDITOR, else nano). Fix a figure
name, cut a line, add context about the piece; save and close, and the show in Atlas is updated. The live narration
loads exactly what is saved here, so people stay in charge of what is said."""
import datetime
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from db import db  # noqa: E402

SPLIT = "\n\n# ---- Rehearsal script: one line each, 'seconds | line'. Edit, add or delete lines. ----\n"


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    shows = db()["shows"]
    show = shows.find_one({"name": sys.argv[1]})
    if not show:
        raise SystemExit(f"no show called {sys.argv[1]!r}; prepare it with scripts/prepare_show.py")
    script = show.get("script") or []
    text = ("# Show notes for " + show["name"] + ". Edit freely; lines starting with # are ignored.\n\n" + show["show_notes"]
            + SPLIT + "\n".join(f"{line['time']:.1f} | {line['text']}" for line in script) + "\n")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(text)
    subprocess.run([os.environ.get("EDITOR", "nano"), f.name], check=True)
    edited = Path(f.name).read_text()
    if edited == text:
        print("no changes")
        return
    notes, _, lines = edited.partition(SPLIT.strip("\n"))
    notes = "\n".join(l for l in notes.splitlines() if not l.startswith("#")).strip()
    new_script = []
    for raw in lines.splitlines():
        if "|" in raw and not raw.startswith("#"):
            t, line = raw.split("|", 1)
            try:
                new_script.append({"time": float(t), "text": line.strip()})
            except ValueError:
                print(f"skipped (no time): {raw}")
    shows.update_one({"_id": show["_id"]}, {"$set": {
        "show_notes": notes, "script": sorted(new_script, key=lambda l: l["time"]),
        "edited": datetime.datetime.now(datetime.timezone.utc)}})
    print(f"saved {show['name']}: notes {len(notes)} characters, {len(new_script)} script lines")


if __name__ == "__main__":
    main()
