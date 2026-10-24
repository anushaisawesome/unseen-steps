"""Copy the narration code the live venue page uses into web/api/_unseen/, for the Vercel functions.

    python scripts/web_sync_server.py

The deploy root is web/, so the functions can't import server/ or scripts/ directly. This copies the server
modules, and takes the live briefs (LIVE_BRIEF, NOTES_BRIEF) out of scripts/live.py, so the website always uses
the same wording as the desktop live program. Run it before every deploy; edit the originals, never the copies.
"""

import ast
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ["narrate.py", "writer.py", "checker.py", "speech.py", "retry.py", "settings.py"]
BRIEFS = ["LIVE_BRIEF", "NOTES_BRIEF", "CLIP_SECONDS", "CLIP_FPS", "NOTES_EVERY", "DIRECTOR"]

out = ROOT / "web/api/_unseen"
out.mkdir(parents=True, exist_ok=True)
for name in MODULES:
    text = (ROOT / "server" / name).read_text(encoding="utf-8")
    (out / name).write_text(f"# Copied from server/{name} by scripts/web_sync_server.py: edit the original.\n" + text,
                            encoding="utf-8")

live = ast.parse((ROOT / "scripts/live.py").read_text(encoding="utf-8"))
values = {n.targets[0].id: n.value.value for n in live.body
          if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in BRIEFS}
missing = set(BRIEFS) - set(values)
if missing:
    raise SystemExit(f"scripts/live.py no longer defines {sorted(missing)}: update this script")
(out / "live_briefs.py").write_text(
    "# Taken from scripts/live.py by scripts/web_sync_server.py: edit the original.\n"
    + "".join(f"{k} = {values[k]!r}\n" for k in BRIEFS), encoding="utf-8")
print(f"copied {len(MODULES)} modules and {len(BRIEFS)} live settings to {out.relative_to(ROOT)}")
