"""Run Argon's style self-check on every demo's map and update the labels on the page (no re-render)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "scripts"))
from director import performance_map  # noqa: E402
from youtube_demo import OUT, VIDEOS  # noqa: E402

videos = {v[0]: v for v in VIDEOS}
for name in ("data.json", "data-keymoments.json"):
    path = OUT / name
    if not path.exists():
        continue
    data = json.loads(path.read_text())
    for entry in data:
        v = videos.get(entry["key"])
        if v:
            plan = performance_map(f"https://www.youtube.com/watch?v={v[1]}", style_hint=v[3], start=v[4], end=v[5])
            entry["style"] = plan["style"]["name"]
            print(f"{entry['key']}: {entry['style']}")
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    path.with_suffix(".js").write_text("window.DEMOS = " + json.dumps(data, ensure_ascii=False) + ";\n")
