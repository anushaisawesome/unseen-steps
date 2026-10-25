"""Re-place the lines of finished YouTube demos with the key-moment-first rule (no rewriting, no new voice).

Usage: python scripts/replace_lines.py [data.json] [key ...]
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from youtube_demo import OUT, place  # noqa: E402

path = OUT / (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else "data.json")
keys = {a for a in sys.argv[1:] if not a.endswith(".json")}
data = json.loads(path.read_text())
for entry in data:
    if keys and entry["key"] not in keys:
        continue
    for l in entry["lines"]:  # lines dropped only for room come back as candidates (their voice clip is on disk)
        clip = f"audio/{entry['key']}-{hashlib.sha1(('v2' + l['text']).encode()).hexdigest()[:10]}.mp3"
        if not l.get("audio") and l.get("status") in ("no room", "gave way to a key moment") and (OUT / clip).exists():
            l["audio"], l["status"] = clip, "spoken"
    place(entry["lines"])
    entry["lines"].sort(key=lambda l: l["at"])
    print(entry["key"], sum(1 for l in entry["lines"] if l.get("audio")), "spoken")
path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
path.with_suffix(".js").write_text("window.DEMOS = " + json.dumps(data, ensure_ascii=False) + ";\n")
