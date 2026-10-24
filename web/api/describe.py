"""Live venue narration (Vercel function): one phrase's measurements in, a checked line (and its voice) out.

The browser runs YOLO pose on the camera and sends only the measurements for the phrase that just ended
(no video). This runs the same loop as the rest of Unseen Steps (server/narrate.py), with a faster model so it keeps up
live: Gemini writes a line, checker.py tests it against the measurements, one rewrite, else silence. With voice "gemini" the line is
also spoken by Gemini TTS (server/speech.py's synthesis step) and returned as WAV.

Needs GEMINI_API_KEY in the Vercel project's environment variables. The page is open to anyone, so every
line is billed to that key: keep a spending cap on its Google billing account.
"""

import base64
import json
import sys
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_unseen"))
import writer  # noqa: E402
from checker import check  # noqa: E402
from google.genai import types  # noqa: E402
# Live voice: one Gemini TTS call. speech.speak() also trims silences with ffmpeg (not on Vercel) and
# transcribes each clip to check it (another second per line): right for recorded renders, too slow live.
from speech import _synthesise  # noqa: E402

# Live needs a line within about a second, so it uses the lite model without extended thinking (about 0.5 s a
# line, against about 2 s for writer.py's model). Same instructions, prompt, checker and one rewrite.
LIVE_MODEL = "gemini-3.5-flash-lite"
LIVE_WORDS = 8

MAX_BODY = 20_000
# Live lines are written from measurements alone (no frames leave the device), so the writer can't see who it is.
NOTES = ("Live: you have only body measurements, no images. Don't guess gender, appearance or costume; "
         "say \"the dancer\" or \"they\". A listener is waiting for each line, so say something every phrase "
         "unless tracking is poor: if little has changed, briefly describe the current position, facing or arm "
         "shape instead of staying silent. At most 8 words: it's spoken live, so short is better. Describe only what the measurements show: if legs_in_view is false, the "
         "legs are out of frame, so say nothing about legs, feet, kicks, jumps or level.")
# What the checker and writer use; anything else the browser sends is dropped.
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


def live_line(features: dict, previous: list[str]) -> tuple[str | None, list[dict]]:
    """server/narrate.describe() with the fast model: write, check, one rewrite with the reason, else silence."""
    attempts, feedback = [], None
    for _ in range(2):
        response = writer.client().models.generate_content(
            model=LIVE_MODEL,
            contents=[writer.build_prompt(features, previous, NOTES, [], feedback)],
            config=types.GenerateContentConfig(system_instruction=writer.SYSTEM, response_mime_type="application/json",
                                               response_schema=writer.RESPONSE_SCHEMA),
        )
        draft = (json.loads(response.text or "{}").get("line") or "").strip() or None
        if draft is None:
            attempts.append({"draft": None, "passed": True, "reason": "writer chose silence"})
            return None, attempts
        verdict = check(draft, features, LIVE_WORDS + 2)
        attempts.append({"draft": draft, "passed": verdict.passed, "reason": verdict.reason})
        if verdict.passed:
            return draft, attempts
        feedback = verdict.reason
    return None, attempts


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        size = int(self.headers.get("content-length") or 0)
        if size > MAX_BODY:
            return self.reply(413, {"error": "The request is too large."})
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError:
            return self.reply(400, {"error": "The request isn't valid JSON."})

        features = clean(body.get("features") or {})
        previous = [str(p)[:200] for p in (body.get("previous") or [])][-5:]
        try:
            line, attempts = live_line(features, previous)
            out = {"line": line, "attempts": attempts}
            if line and body.get("voice") == "gemini":
                with tempfile.TemporaryDirectory() as d:
                    wav = _synthesise(line, Path(d) / "line.wav")
                    out["audio"] = base64.b64encode(wav.read_bytes()).decode()
        except Exception as e:  # Gemini quota, network: tell the page, which stays silent for this phrase
            return self.reply(502, {"error": f"Narration failed: {type(e).__name__}: {str(e)[:200]}"})
        self.reply(200, out)

    def reply(self, status: int, payload: dict):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
