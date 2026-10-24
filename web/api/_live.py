"""Shared by the live venue functions (describe.py, notes.py). The leading underscore keeps Vercel from serving
it as an endpoint."""

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_unseen"))
from google.genai import types  # noqa: E402

# What the checker uses; anything else the browser sends is dropped.
NUMBERS = ("phrase", "start", "end", "people", "speed", "max_rise", "turns", "arms_up", "stillness")
WORDS = {"tracking": ("good", "ok", "poor"), "lowest_level": ("standing", "low", "floor"),
         "travel": ("left", "right", "none"), "rotation": ("left", "right", "mixed"),
         "facing": ("facing us", "back to us", "side-on", "unclear")}


def clean(features: dict) -> dict:
    out = {}
    for k in NUMBERS:
        if isinstance(features.get(k), (int, float)):
            out[k] = round(float(features[k]), 3)
    for k, allowed in WORDS.items():
        out[k] = features.get(k) if features.get(k) in allowed else None
    out["events"] = [str(e)[:60] for e in (features.get("events") or [])[:12]]
    out["legs_in_view"] = bool(features.get("legs_in_view", True))
    return out


def frame_parts(frames: list, limit: int) -> list:
    """[{"t": seconds, "jpeg": base64}] -> Gemini parts, each frame after its time, oldest first (as live.py)."""
    parts = []
    for f in sorted(frames, key=lambda f: float(f.get("t", 0)))[-limit:]:
        try:
            data = base64.b64decode(f["jpeg"], validate=True)
        except (KeyError, ValueError, TypeError):
            continue
        if data[:2] == b"\xff\xd8":  # JPEG only
            parts += [f"{float(f.get('t', 0)):.1f} s:", types.Part.from_bytes(data=data, mime_type="image/jpeg")]
    return parts


def read_json(handler, max_body: int) -> dict | None:
    """The request body as JSON, or None after replying with the error."""
    size = int(handler.headers.get("content-length") or 0)
    if size > max_body:
        reply(handler, 413, {"error": "The request is too large."})
        return None
    try:
        return json.loads(handler.rfile.read(size) or b"{}")
    except json.JSONDecodeError:
        reply(handler, 400, {"error": "The request isn't valid JSON."})
        return None


def reply(handler, status: int, payload: dict):
    data = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
