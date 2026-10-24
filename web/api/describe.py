"""Live venue narration (Vercel function): the last few seconds of camera frames and pose measurements in,
a checked line (and its voice) out.

The same approach as the desktop live program (scripts/live.py): Gemini sees the last few seconds as frames
(2 a second, sent by the browser) with the pose measurements, what's been said and the director's running notes,
and writes one short line or chooses silence (LIVE_BRIEF); checker.py vets it against the measurements.
One difference: the writer is the lite model, about 1.2 s a line with frames against about 5.4 s for
gemini-3.8-flash, so lines stay live. With voice "gemini" the line is also voiced and returned as WAV.

Needs GEMINI_API_KEY in the Vercel project's environment variables. The page is open to anyone, so every
line is billed to that key: keep a spending cap on its Google billing account.
"""

import base64
import json
import sys
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _live import clean, frame_parts, read_json, reply  # noqa: E402
import writer  # noqa: E402
from checker import check  # noqa: E402
from google.genai import types  # noqa: E402
from live_briefs import LIVE_BRIEF  # noqa: E402
# Live voice: one Gemini TTS call. speech.speak() also trims silences with ffmpeg (not on Vercel) and
# transcribes each clip to check it (another second per line): right for recorded renders, too slow live.
from speech import _synthesise  # noqa: E402

LIVE_MODEL = "gemini-3.5-flash-lite"
MAX_BODY = 2_000_000   # about 8 frames of 512 px JPEG plus measurements
MAX_FRAMES = 10


def live_line(features: dict, frames: list, said: list[str], notes: str, style: str) -> tuple[str | None, list[dict]]:
    """scripts/live.py's describe step: one line from the frames and measurements, or silence; one checker pass."""
    context = (f"Pose measurements for {features.get('start', 0):.1f}-{features.get('end', 0):.1f} s: "
               f"{json.dumps(features)}\n"
               f"Already said: {said or 'nothing yet'}\n"
               f"Director's notes: {notes or 'none yet'}"
               + (f"\nThe style is {style}." if style else ""))
    response = writer.client().models.generate_content(
        model=LIVE_MODEL, contents=[LIVE_BRIEF, *frame_parts(frames, MAX_FRAMES), context],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={"type": "object", "properties": {"line": {"type": "string", "nullable": True}}}),
    )
    line = (json.loads(response.text or "{}").get("line") or "").strip() or None
    if line is None:
        return None, [{"draft": None, "passed": True, "reason": "writer chose silence"}]
    verdict = check(line, features, max_words=10)
    return (line if verdict.passed else None), [{"draft": line, "passed": verdict.passed, "reason": verdict.reason}]


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = read_json(self, MAX_BODY)
        if body is None:
            return
        features = clean(body.get("features") or {})
        said = [str(p)[:200] for p in (body.get("said") or [])][-6:]
        notes = str(body.get("notes") or "")[:2000]
        style = str(body.get("style") or "")[:60]
        try:
            line, attempts = live_line(features, body.get("frames") or [], said, notes, style)
            out = {"line": line, "attempts": attempts}
            if line and body.get("voice") == "gemini":
                with tempfile.TemporaryDirectory() as d:
                    wav = _synthesise(line, Path(d) / "line.wav")
                    out["audio"] = base64.b64encode(wav.read_bytes()).decode()
        except Exception as e:  # Gemini quota, network: tell the page, which stays silent for this stretch
            return reply(self, 502, {"error": f"Narration failed: {type(e).__name__}: {str(e)[:200]}"})
        reply(self, 200, out)
