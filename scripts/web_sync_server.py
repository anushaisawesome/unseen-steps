"""Copy the narration modules the live venue page uses into web/api/_unseen/, for the Vercel function.

    python scripts/web_sync_server.py

The deploy root is web/, so the function can't import server/ directly. Run this before every deploy;
edit the files in server/, never the copies.
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ["narrate.py", "writer.py", "checker.py", "speech.py", "retry.py", "settings.py"]

out = ROOT / "web/api/_unseen"
out.mkdir(parents=True, exist_ok=True)
for name in MODULES:
    text = (ROOT / "server" / name).read_text(encoding="utf-8")
    (out / name).write_text(f"# Copied from server/{name} by scripts/web_sync_server.py: edit the original.\n" + text,
                            encoding="utf-8")
print(f"copied {len(MODULES)} modules to {out.relative_to(ROOT)}")
