"""The director: Gemini 4 Argon watches the whole performance and builds a performance map.

Flash can describe one phrase; only Argon holds the whole piece in one context. It returns the
style (with evidence, so a person can confirm it), the sections, the motifs that recur (with the
times they appear), and the key moments. Every key moment that makes a checkable claim (a jump, a
turn, going to the floor, a pause, travelling left or right) is cross-checked against the pose
measurements for that time; claims the measurements don't support are dropped, never spoken.

The writer then gets short notes for each phrase: which section it's in, which motifs appear (and
when they first appeared, so lines can call back to them), and the verified moments.

Usage:
    python server/director.py clips/ballet.mp4
"""

import hashlib
import json
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

try:
    from .retry import with_retry
except ImportError:
    from retry import with_retry
try:
    from .settings import gemini_api_key
except ImportError:  # Running as ``python server/director.py``.
    from settings import gemini_api_key

MODEL = "gemini-4-argon"
CACHE = Path(__file__).resolve().parents[1] / "data" / "director"

PROMPT = """You are directing live audio description of this dance for blind audience members.
Watch the whole performance and return JSON with:
- style: {name, confidence 0 to 1, evidence: short visible cues, e.g. "pointe shoes", "closed hold"}
- sections: [{start, end, label, description, formation, group, techniques}] the structure of the piece, in seconds.
  formation: where dancers are (lines, wedge, V, circle, clusters, scattered; which side). group: how they move
  together (unison, canon and the direction it ripples, a soloist against the group, pairs, subgroups trading).
  techniques: [{name, evidence}] the dance techniques used, each with what the body visibly does (e.g. tutting:
  forearms and hands make sharp right angles and boxes; floorwork: rolls, slides, spins on the floor). Be precise
  about technique versus mime: a geometric hand shape that suggests an image is still the technique. If the piece
  fuses styles, name the style each technique comes from, the way an expert dancer would: consider the traditions it
  could come from worldwide (classical and folk as well as street and studio), weigh the visible evidence (hands,
  stance, footwork, head and eyes, torso) and the context in the video (on-screen names, flags, music, costume), and
  name the one the evidence supports best rather than the first label that roughly fits, but only when several
  distinct cues clearly support it; when the evidence is thin, describe the movement plainly instead of guessing.
- signature: [{quality, body, dynamics, times: [seconds]}] the two to four things a sighted viewer notices and
  remembers most about this particular choreography (not the style in general): what it is, where it lives in the
  body (head, hair, face, arms, hands, torso, hips, legs, feet and footwork), its dynamics and texture, and the times
  it is strongest.
- dynamics: [{start, end, texture, energy, music}] a timeline of the quality of movement covering the whole piece,
  with a new entry whenever it changes, even inside a section: texture (e.g. sharp staccato hits, fluid sustained
  waves, heavy grounded drops, light suspended), energy (low, building, high, release) and what the music is doing
  then. A sighted viewer feels these shifts even without words for them; mark each one at the moment it happens.
- motifs: [{name, description, times: [seconds]}] movements that recur; give every time each one appears
- moments: [{time, what, claim}] the most striking moments, including the big accents with the music (a hit, a
  clap, a turn into a new phrase, a freeze, the moment the vocals or the beat come in), described in body terms with
  direction as the audience sees it ("to the left"). claim is one of: jump, turn, floor, still, travel_left,
  travel_right, other.
Only state what you can see. Use a dance term only if you are confident it is correct for this style;
otherwise describe the shape plainly."""

SCHEMA = {
    "type": "object",
    "properties": {
        "style": {"type": "object", "properties": {
            "name": {"type": "string"}, "confidence": {"type": "number"},
            "evidence": {"type": "array", "items": {"type": "string"}}},
            "required": ["name", "confidence", "evidence"]},
        "sections": {"type": "array", "items": {"type": "object", "properties": {
            "start": {"type": "number"}, "end": {"type": "number"},
            "label": {"type": "string"}, "description": {"type": "string"},
            "formation": {"type": "string"}, "group": {"type": "string"},
            "techniques": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["name", "evidence"]}}},
            "required": ["start", "end", "label", "description", "formation", "group", "techniques"]}},
        "dynamics": {"type": "array", "items": {"type": "object", "properties": {
            "start": {"type": "number"}, "end": {"type": "number"}, "texture": {"type": "string"},
            "energy": {"type": "string"}, "music": {"type": "string"}},
            "required": ["start", "end", "texture", "energy", "music"]}},
        "signature": {"type": "array", "items": {"type": "object", "properties": {
            "quality": {"type": "string"}, "body": {"type": "string"}, "dynamics": {"type": "string"},
            "times": {"type": "array", "items": {"type": "number"}}},
            "required": ["quality", "body", "dynamics", "times"]}},
        "motifs": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "description": {"type": "string"},
            "times": {"type": "array", "items": {"type": "number"}}},
            "required": ["name", "description", "times"]}},
        "moments": {"type": "array", "items": {"type": "object", "properties": {
            "time": {"type": "number"}, "what": {"type": "string"},
            "claim": {"type": "string", "enum": ["jump", "turn", "floor", "still", "travel_left", "travel_right", "other"]}},
            "required": ["time", "what", "claim"]}},
    },
    "required": ["style", "sections", "signature", "dynamics", "motifs", "moments"],
}

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=gemini_api_key())
    return _client


_uploads = {}


def upload(video: str):
    """Upload a video to the Files API (once per file) and wait until Gemini can watch it."""
    if video in _uploads:
        return _uploads[video]
    uploaded = client().files.upload(file=video)
    while uploaded.state.name == "PROCESSING":
        time.sleep(2)
        uploaded = client().files.get(name=uploaded.name)
    _uploads[video] = uploaded
    return uploaded


FPS = 5  # Gemini's default is 1 frame a second, too few to see sharp vs fluid movement, hits or arm detail


def video_part(video: str, start: float | None = None, end: float | None = None, fps: int | None = None):
    """A video Gemini can watch at FPS frames a second: a local file (uploaded) or a public YouTube link (read by
    Gemini directly, never downloaded), optionally clipped to start..end seconds."""
    clip = types.VideoMetadata(fps=fps or FPS, start_offset=f"{start or 0:.1f}s" if start is not None else None,
                               end_offset=f"{end:.1f}s" if end else None)
    if video.startswith("http"):
        return types.Part(file_data=types.FileData(file_uri=video), video_metadata=clip)
    uploaded = upload(video)
    return types.Part(file_data=types.FileData(file_uri=uploaded.uri, mime_type=uploaded.mime_type), video_metadata=clip)


def clip_note(start: float | None, end: float | None) -> str:
    if start is None and end is None:
        return ""
    return (f"\nOnly the part of the video from {start or 0:.0f} s to {end:.0f} s is shown. Give every time as the "
            "time in the full video (seconds from its very beginning), not from the start of the part.")


def source_key(video: str) -> bytes:
    """Identifies what Argon watched (the video and the frame rate), for caching."""
    return (video.encode() if video.startswith("http") else Path(video).read_bytes()) + f"@{FPS}fps".encode()


def performance_map(video: str, style_hint: str | None = None, start: float | None = None,
                    end: float | None = None) -> dict:
    """Argon's map of the whole performance. Cached per video file, since a map only changes with the video."""
    # Keyed on the instructions too, so a changed prompt gets a fresh map.
    digest = hashlib.sha1(source_key(video) + PROMPT.encode() + ZOOM.encode() + json.dumps(SCHEMA).encode()
                          + (style_hint or "").encode() + clip_note(start, end).encode()).hexdigest()[:16]
    cached = CACHE / f"{digest}.json"
    if cached.exists():
        return json.loads(cached.read_text())

    watched = video_part(video, start, end)
    prompt = PROMPT + (f"\nThe person who uploaded it says the style is: {style_hint}. Treat that as a hint, "
                       "not a fact; if the video clearly shows otherwise, say so in style." if style_hint else "") + clip_note(start, end)
    response = with_retry(lambda: client().models.generate_content(
        model=MODEL,
        contents=[watched, prompt],
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="medium"),
            response_mime_type="application/json",
            response_schema=SCHEMA,
        ),
    ))
    result = zoom(video, json.loads(response.text), start, end)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(result, indent=2))
    return result


ZOOM = """Zoom in on this section of the dance (the rest of the piece is mapped already). Watch closely and describe,
second by second, with times in the full video: what each dancer does; every technique and which style it comes from
(name each influence in a fusion); what the whole body does, from top to bottom: head, hair and face, arms, hands
and wrists, torso and hips, legs and feet (footwork and its rhythm, stamps, kicks, extensions, turnout, weight
changes), including performance details such as hand performance and head and hair whips; the texture and dynamics and exactly when they change (sharp to fluid, still to explosive); the shapes at
holds and hits; formations, unison and canons; the big accents with the music. Only what you can see. Plain text.

Name influences the way an expert dancer would: before settling on a style for a movement or pose, consider the dance
traditions it could come from worldwide (classical and folk forms as well as street and studio styles), weigh the
visible evidence for each (the hand shapes, the stance and its turnout, the footwork, the head, neck and eyes, the
torso), and the context in the video itself (on-screen names, flags, the music, the costume). Name the influence the
evidence supports best, in that tradition's own terms, rather than the first label that roughly fits; but only when
several distinct cues clearly support it. When the evidence is thin, describe the movement plainly instead of guessing
a tradition. Where the style has its own framework of named elements or parts, use it."""


def zoom(video: str, plan: dict, start: float | None, end: float | None) -> dict:
    """A close look at each section at 8 frames a second: one pass over a long piece skims the detail."""
    from concurrent.futures import ThreadPoolExecutor

    def look(section):
        a, b = section["start"], section["end"]
        if b - a < 3:
            return ""
        r = with_retry(lambda: client().models.generate_content(
            model=MODEL, contents=[video_part(video, a, b, fps=8),
                                   ZOOM + f"\nThis section runs from {a:.1f} s to {b:.1f} s ({section['label']})."],
            config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="low"))))
        return r.text.strip()

    with ThreadPoolExecutor(max_workers=4) as pool:
        details = list(pool.map(look, plan["sections"]))
    for section, detail in zip(plan["sections"], details):
        section["detail"] = detail
    return plan


# What each claim needs to see in the measured features of the phrase it falls in.
SUPPORTED = {
    "jump": lambda f: (f.get("max_rise") or 0) >= 0.05,
    "turn": lambda f: (f.get("turns") or 0) >= 1,
    "floor": lambda f: f.get("lowest_level") in ("floor", "low"),
    "still": lambda f: (f.get("stillness") or 0) >= 0.3,
    "travel_left": lambda f: f.get("travel") == "left",
    "travel_right": lambda f: f.get("travel") == "right",
}


def cross_check(plan: dict, phrases: list[dict]) -> dict:
    """Mark each key moment as verified, dropped (the measurements contradict it) or unchecked (no claim
    the pose data can test, or no tracking at that time). Only verified and unchecked moments reach the writer."""
    for moment in plan["moments"]:
        phrase = next((f for f in phrases if f["start"] <= moment["time"] < f["end"]), None)
        test = SUPPORTED.get(moment["claim"])
        if phrase is None or phrase.get("tracking") == "poor" or test is None:
            moment["check"] = "unchecked"
        else:
            moment["check"] = "verified" if test(phrase) else "dropped"
    return plan


def notes_for(plan: dict, start: float, end: float) -> str:
    """Short notes for the writer about one phrase: section, recurring motifs (with callbacks), verified moments."""
    lines = []
    section = next((s for s in plan["sections"] if s["start"] <= start < s["end"]), None)
    if section:
        lines.append(f"Section: {section['label']}" + (f" ({section['description']})" if section.get("description") else ""))
    for motif in plan["motifs"]:
        here = [t for t in motif["times"] if start <= t < end]
        earlier = [t for t in motif["times"] if t < start]
        if here and earlier:
            lines.append(f"Recurring motif returns: {motif['name']} ({motif['description']}), first seen at {earlier[0]:.0f} s")
        elif here:
            lines.append(f"Motif starts here: {motif['name']} ({motif['description']})")
    for moment in plan["moments"]:
        if start <= moment["time"] < end and moment.get("check") != "dropped":
            lines.append(f"Key moment at {moment['time'] - start:.1f} s into the phrase: {moment['what']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(json.dumps(performance_map(sys.argv[1]), indent=2))
