"""Argon writes the audio description script; pose and music time it and check it.

This is how dance audio description is really done: a describer prepares a script from a recording
(the rehearsal, or the uploaded video), then it is delivered in time with the performance. Argon
watches and listens to the whole video, with the music map (energy per bar, quiet gaps, hits) and the
style's glossary, and writes timed lines, each with a pace and a delivery note: calm and spacious in
lyrical passages, rapid callouts on the hits when the music explodes ("Hit above the head! To the
side! Fold to the right!"). Every line names the time range of the movement it describes, so the
pose measurements for that range can check it (checker.py); lines the measurements contradict go back
to Argon once to revise, else stay silent.

Usage:
    python server/scriptwriter.py clips/ballet.mp4
"""

import hashlib
import json
import sys
from pathlib import Path

from google.genai import types

try:
    from .director import CACHE, MODEL, clip_note, client, source_key, video_part
    from .retry import with_retry
except ImportError:
    from director import CACHE, MODEL, clip_note, client, source_key, video_part
    from retry import with_retry

# Words per second at each pace (the voice is time-stretched to fit, up to about 1.35x). There is no slow pace:
# slow lines drag and pull attention off the music.
RATE = {"steady": 2.8, "brisk": 3.2, "rapid": 3.8}

BRIEF = """You are an expert audio describer for dance, preparing the audio description for blind and partially
sighted audience members from this recording (watch and listen). It is spoken over the music. Write the script.

What to say, like the best dance describers:
- First, what makes this piece this piece. Your first viewing (below) names its signature: the qualities a sighted
  viewer notices and remembers most. Every one of them must come through, at the moments it's strongest, in
  specific body language: where the movement lives in the body (arms, hands, torso, hips, legs, feet, head, gaze),
  its dynamics (sharp or sustained, light or strong, bound or free), its texture and its relationship to the music.
  A listener who can't see should come away with the same impression of the choreography as someone who can.
- Use the style's own vocabulary, accurately, for steps and techniques; the first time a term appears, add a few
  plain words so a newcomer can picture it. A term carries its definition: use it only when every part of the
  definition is visible, and never borrow one style's term for another style's movement. Ballet terms in particular
  require turnout: a plié is bent knees with the legs rotated out from the hips, knees over turned-out feet, and the
  positions (first, second, fifth...) are turned out too. Bent legs with knees forward or turned in are "bent knees",
  "a deep squat" or "a wide stance", or that style's own word. Name the technique a dancer is doing even when its shape suggests an
  image, and give the image only as a comparison. If the piece fuses styles, notice each influence as it appears,
  use that style's language for it, and say when the piece shifts between influences.
- Capture expression: the feeling the movement gives, grounded in what is visible. Vivid, plain words, not purple
  prose.
- Say where dancers are and how they relate: facing, travel, formations, unison or canon (the same move rippling
  through dancers one after another, and which way it travels), a soloist breaking out, pairs forming. Directions
  as the audience sees them ("to the left"), never "stage left" or "stage right".
- Follow the structure of the piece given below. Every section gets at least one line: a listener must hear when
  the piece changes.
- Every change in the dynamics timeline is priority 1: say the shift as it happens, so the listener feels the
  texture change (what it changes from and to), not just the new steps.
- Spend words on what matters most, never on what is generic or incidental, and never repeat a description.
  Present tense. Only describe what you can see; if unsure of a term, describe the shape plainly.

How and when to say it: the music is the star, the description is tasteful commentary inside it.
- Where a step or technique has a name, lead with it: a name carries the most in the fewest words. Add a few
  plain words only where they help picture it.
- Be sparse and short. Most lines are 3 to 8 words and fit inside one bar; a few may take two bars. Speak for at
  most a third of the running time overall; in lyrical passages, at most one line every two bars. Leave the rest
  to the music. Never narrate continuously and never read like a speech.
- Stay in meter: every line starts on a beat and lasts a whole number of beats (see the beat grid below), so it
  sits inside the music's phrasing rather than across it. Prefer the quieter gaps.
- Match the music's energy. Lyrical passages: occasional short, steady lines. Builds: brisk. When the music
  explodes (a big chorus, a run of hard hits), call the movement on the hits in bursts of two to five words, e.g.
  "Hit above the head! To the side! Fold to the right!" Each burst is its own line, on its hit.
- time is the beat the line starts on: just after the movement it describes, or on the hit for callouts.
- Lines never overlap. Rates in words per second: steady 2.8, brisk 3.2, rapid 3.8.
- delivery: a short tone note for the voice (under 10 words), e.g. "light, warm" or "punchy, explosive". Never slow
  or drawn out.

For each line give: time, moment_start and moment_end (seconds: the movement it describes), who (solo, pair,
group or subgroup), kind (description or callout), pace (steady, brisk or rapid), delivery, priority (1 = a listener
would miss something important without it, 2 = helpful, 3 = optional colour). Priority 1 is only for the opening
line (scene and starting position), the first line of each section, canons or formation changes, and lines that
carry the piece's signature. Most other
lines, including ones that name steps, are 2), and text."""

SCHEMA = {
    "type": "object",
    "properties": {
        "style": {"type": "string"},
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "time": {"type": "number"}, "moment_start": {"type": "number"}, "moment_end": {"type": "number"},
            "who": {"type": "string", "enum": ["solo", "pair", "group", "subgroup"]},
            "kind": {"type": "string", "enum": ["description", "callout"]},
            "pace": {"type": "string", "enum": list(RATE)},
            "delivery": {"type": "string"}, "priority": {"type": "integer"}, "text": {"type": "string"}},
            "required": ["time", "moment_start", "moment_end", "who", "kind", "pace", "delivery", "priority", "text"]}},
    },
    "required": ["style", "lines"],
}

REVIEW = """You are a second expert dance describer reviewing a colleague's audio description script for blind and
partially sighted listeners, against the video (watch and listen). The first viewing's map of the piece and the
script are below.

Ask: what would a blind listener miss that a sighted viewer gets from this choreography? Look for signature
qualities that don't come through (where the movement lives in the body, its dynamics, texture, musicality),
group structure or striking moments that are missing, lines that are generic, inaccurate or misname a technique
(check every technical term against its definition: a term whose definition isn't fully visible, or a term borrowed
from another style, must be replaced with plain words; for example a plié or a ballet position needs visible
turnout), and words spent on what matters less. Keep the same rules as the script: lines stay short (most 3 to 8 words, inside one
bar; callouts 2 to 5 words); a richer line is a better-chosen word, not a longer line. Callouts on the hits, the
music stays the main thing, so prefer replacing a weaker line over adding one.

Return JSON {"notes": "one or two sentences on what was missing", "edits": [...]}, at most 10 edits, each one of:
{"action": "replace", "time": t, "text": "...", ...} (the line starting nearest t),
{"action": "add", "time": t, "moment_start": s, "moment_end": e, "text": "...", ...},
{"action": "drop", "time": t}.
replace and add also give kind, pace, delivery, priority and who, as in the script.

"""

REVISE = """These lines from your audio description script break a rule (they contradict the pose measurements for
the moment they describe, or they're too long for the time they have). Revise each so it keeps to the rule, keeping
what matters most in it and its expressiveness, or return null for it if you can't. Return JSON: {"lines": [{"time": t, "text": "..." or null}]}.

"""


def music_notes(song: dict) -> str:
    """The music map in a form Argon can use alongside what it hears."""
    energy = " ".join(f"{t:.0f}s:{e:.1f}" for t, e in song["energy"])
    gaps = " ".join(f"{s[0]:.1f}-{s[1]:.1f}" for s in song["clean_spaces"] if s)
    hits = " ".join(f"{h:.1f}" for h in song["hits"])
    beat = (song["beats"][-1] - song["beats"][0]) / max(1, len(song["beats"]) - 1)
    bar = beat * song["beats_per_bar"]
    return (f"Music: {song['bpm']} bpm, {song['beats_per_bar']} beats per bar: a beat is {beat:.2f} s, a bar is "
            f"{bar:.2f} s, so one bar holds about {int(bar * RATE['steady'])} words at a steady pace.\n"
            f"Beat grid: the first beat is at {song['beats'][0]:.2f} s; bars start at the times listed under energy.\n"
            f"Energy per bar (bar start: 0 quietest to 1 loudest): {energy}\n"
            f"Quieter gaps good for fuller lines (seconds): {gaps}\n"
            f"Strongest hits (seconds): {hits}")


def room(song: dict | None, start: float | None, end: float | None) -> str:
    """How many lines the music has room for, so Argon chooses them (with taste) instead of a cutter later."""
    if song:
        length = song["beats"][-1] - song["beats"][0]
    elif end:
        length = end - (start or 0)
    else:
        return ""
    seconds = 0.35 * length
    return (f"\nRoom: this piece runs {length:.0f} s, so the speech should total about {seconds:.0f} s. A description "
            "line takes about 3 s; a callout takes about 1 s, so a sharp, hit-driven passage can carry several callouts. "
            "Spend the time on the signature and the key moments, call the big accents on the music (a hit, a clap, a "
            "turn into a new phrase) as they land, and leave the rest to the music. Silence belongs where the movement "
            "repeats or rests: never more than about 6 s of quiet while new movement is happening.")


def structure_notes(plan: dict) -> str:
    """The director's performance map as text: sections with formation, group structure and techniques; motifs."""
    out = [f"Signature of this piece (must come through):"]
    for sig in plan.get("signature", []):
        out.append(f"- {sig['quality']}: {sig['body']}; {sig['dynamics']}; strongest at "
                   + ", ".join(f"{t:.0f} s" for t in sig["times"]))
    out.append("Dynamics timeline (every change of texture or energy is a key moment):")
    for d in plan.get("dynamics", []):
        out.append(f"- {d['start']:.0f}-{d['end']:.0f} s: {d['texture']}; energy {d['energy']}; music: {d['music']}")
    if plan.get("measured_texture"):
        out.append("Texture changes measured from the pose tracking (sudden stops and starts in the joints vs smooth, "
                   "continuous motion): " + "; ".join(plan["measured_texture"]))
    out.append(f"Structure of the piece (style: {plan['style']['name']}):")
    for sec in plan["sections"]:
        techniques = "; ".join(f"{t['name']} ({t['evidence']})" for t in sec.get("techniques", []))
        out.append(f"- {sec['start']:.0f}-{sec['end']:.0f} s, {sec['label']}: {sec.get('description', '')} "
                   f"Formation: {sec.get('formation', '')}. Group: {sec.get('group', '')}. Techniques: {techniques}.")
    for motif in plan.get("motifs", []):
        out.append(f"- Motif \"{motif['name']}\" ({motif['description']}) at " + ", ".join(f"{t:.0f} s" for t in motif["times"]))
    return "\n".join(out)


def write_script(video: str, song: dict | None, glossary: list[str] = (), style_hint: str | None = None,
                 plan: dict | None = None, start: float | None = None, end: float | None = None) -> dict:
    """Argon's whole script, cached per video, music map, glossary and performance map. Without a music map
    (a YouTube link we can't analyse), Argon keeps time by ear."""
    prompt = BRIEF + "\n\n" + (music_notes(song) if song else
                                "No beat grid is available: listen to the music and start each line on a beat yourself.")
    prompt += clip_note(start, end) + room(song, start, end)
    if plan:
        prompt += "\n\n" + structure_notes(plan)
    if glossary:
        prompt += ("\n\nGlossary vetted by dancers for this style (use these names where they fit):\n"
                   + "\n".join(f"- {g}" for g in glossary))
    if style_hint:
        prompt += f"\n\nThe person who uploaded it says the style is {style_hint}; treat that as a hint, not a fact."
    key = hashlib.sha1(source_key(video)[:50_000_000] + prompt.encode()).hexdigest()[:16]
    cached = CACHE / f"script-{key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    response = with_retry(lambda: client().models.generate_content(
        model=MODEL,
        contents=[video_part(video, start, end), prompt],
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="high"),
            response_mime_type="application/json",
            response_schema=SCHEMA,
        ),
    ))
    script = json.loads(response.text)
    script["lines"] = in_meter(script["lines"], song["beats"]) if song else \
        sorted(script["lines"], key=lambda l: l["time"])
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(script, indent=2, ensure_ascii=False))
    return script


def in_meter(lines: list[dict], beats: list[float]) -> list[dict]:
    """Start every line on a beat (the nearest one, never more than half a beat early), in order, and drop a line
    whose beat is already taken by the line before it."""
    import bisect
    out, taken = [], -1
    for line in sorted(lines, key=lambda l: l["time"]):
        k = bisect.bisect_left(beats, line["time"])
        if k > 0 and (k == len(beats) or line["time"] - beats[k - 1] < beats[k] - line["time"]):
            k -= 1
        if k <= taken:
            k = taken + 1
        if k >= len(beats):
            break
        out.append({**line, "time": beats[k], "asked_time": line["time"]})
        taken = k
    return out


def review_script(video: str, script: dict, plan: dict | None, song: dict | None = None,
                  start: float | None = None, end: float | None = None) -> dict:
    """A second Argon pass watches the video with the script and fixes what a blind listener would miss. Cached."""
    listing = "\n".join(f"{l['time']:.1f} s [{l['kind']}, {l['pace']}, priority {l.get('priority')}] {l['text']}"
                         for l in script["lines"])
    prompt = (REVIEW + (structure_notes(plan) + "\n\n" if plan else "") + "Script:\n" + listing + clip_note(start, end)
              + room(song, start, end) + " Keep the total speaking time about the same: for every line you add, drop or "
              "merge a weaker one. Check especially that the signature comes through, that every change of texture or energy in the "
              "dynamics timeline is felt at the moment it happens, and that the big accents are called.")
    key = hashlib.sha1(source_key(video)[:50_000_000] + prompt.encode()).hexdigest()[:16]
    cached = CACHE / f"review-{key}.json"
    if cached.exists():
        review = json.loads(cached.read_text())
    else:
        response = with_retry(lambda: client().models.generate_content(
            model=MODEL,
            contents=[video_part(video, start, end), prompt],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="high"),
                response_mime_type="application/json",
            ),
        ))
        review = json.loads(response.text)
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(review, indent=2, ensure_ascii=False))

    lines = [dict(l) for l in script["lines"]]
    for edit in review.get("edits", [])[:10]:
        near = min(lines, key=lambda l: abs(l["time"] - edit.get("time", 0)), default=None)
        if edit.get("action") in ("replace", "drop") and (near is None or abs(near["time"] - edit["time"]) > 1.5):
            continue
        if edit["action"] == "drop":
            lines.remove(near)
        elif edit["action"] == "replace" and edit.get("text"):
            near.update({k: v for k, v in edit.items() if k in ("text", "kind", "pace", "delivery", "priority", "who")},
                        reviewed=True)
        elif edit["action"] == "add" and edit.get("text"):
            t = edit["time"]
            lines.append({"time": t, "moment_start": edit.get("moment_start", t - 2), "moment_end": edit.get("moment_end", t),
                          "who": edit.get("who", "solo"), "kind": edit.get("kind", "description"),
                          "pace": edit.get("pace", "steady"), "delivery": edit.get("delivery", ""),
                          "priority": edit.get("priority", 1), "text": edit["text"], "reviewed": True})
    lines = [l for l in lines if l.get("pace") in RATE] + [dict(l, pace="steady") for l in lines if l.get("pace") not in RATE]
    lines = in_meter(lines, song["beats"]) if song else sorted(lines, key=lambda l: l["time"])
    return {**script, "lines": lines, "review": review.get("notes", "")}


def budget(lines: list[dict], end: float) -> list[int]:
    """Most words each line can have before the next one starts, at its pace (with 30% stretch allowed)."""
    out = []
    for n, line in enumerate(lines):
        until = lines[n + 1]["time"] if n + 1 < len(lines) else end
        out.append(max(2, int((until - line["time"] - 0.2) * RATE.get(line["pace"], 2.8) * 1.3)))
    return out


def revise(rejected: list[dict]) -> dict[float, str | None]:
    """Send lines the checker rejected back to Argon once. rejected: [{time, text, reason}]."""
    if not rejected:
        return {}
    listing = "\n".join(f"at {r['time']} s: \"{r['text']}\" -- {r['reason']}" for r in rejected)
    response = with_retry(lambda: client().models.generate_content(
        model=MODEL,
        contents=REVISE + listing,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            response_mime_type="application/json",
        ),
    ))
    return {float(l["time"]): l.get("text") for l in json.loads(response.text).get("lines", [])}


if __name__ == "__main__":
    from music import load_audio, map_song
    song = map_song(load_audio(sys.argv[1]), bars_per_phrase=2, speech_seconds=3.0, earliest=True)
    script = write_script(sys.argv[1], song)
    print(script["style"])
    for line in script["lines"]:
        print(f"{line['time']:6.1f}s  [{line['pace']}, {line['delivery']}]  {line['text']}")
