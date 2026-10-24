"""Live venue director (Vercel function): the last ~20 seconds of camera frames in, Argon's updated running
notes out (style, this dancer's signature, motifs, what just changed), for the live describer.

The same step as scripts/live.py's direct(), with its brief and model. The page calls it in the background
about every 20 s, so it never holds up a line.
"""

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _live import frame_parts, read_json, reply  # noqa: E402
import writer  # noqa: E402
from google.genai import types  # noqa: E402
from live_briefs import DIRECTOR, NOTES_BRIEF  # noqa: E402

MAX_BODY = 4_000_000   # about 40 frames of 512 px JPEG
MAX_FRAMES = 40


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = read_json(self, MAX_BODY)
        if body is None:
            return
        previous = str(body.get("notes") or "")[:2000]
        style = str(body.get("style") or "")[:60]
        parts = frame_parts(body.get("frames") or [], MAX_FRAMES)
        if not parts:
            return reply(self, 200, {"notes": previous})
        try:
            response = writer.client().models.generate_content(
                model=DIRECTOR,
                contents=[NOTES_BRIEF, *parts, f"Your previous notes:\n{previous or 'none yet'}"
                          + (f"\nThe style is {style}." if style else "")],
                config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="low")),
            )
        except Exception as e:
            return reply(self, 502, {"error": f"Director failed: {type(e).__name__}: {str(e)[:200]}"})
        reply(self, 200, {"notes": (response.text or "").strip()})
