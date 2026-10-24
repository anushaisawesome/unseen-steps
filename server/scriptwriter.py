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
- Name what dancers do in the style's own vocabulary, accurately (ballet: positions such as fifth, steps such as
  glissade, sissonne, grand jeté, pas de bourrée, pirouette, port de bras, arabesque, épaulement; ballroom: hold,
  frame, rise and fall, natural/reverse turn; street and commercial: tutting, waacking, popping, body roll, hits,
  and so on). The first time a term appears, add a few plain words so a newcomer can picture it.
- Capture quality, dynamics and expression, not just mechanics: weight (light, grounded), time (sudden,
  sustained), flow (free, bound), shape and line, where the gaze goes, and the feeling (playful, yearning,
  defiant). Ground the feeling in what is visible. Vivid, plain words, not purple prose.
- Say where dancers are and how they relate: facing, travel, and for groups the formation (lines, circles,
  diagonals, wedge), unison or canon, a soloist breaking out, pairs forming. Directions as the audience sees them
  ("to the left"), never "stage left" or "stage right".
- Follow the structure of the piece given below (from your first viewing). Every section gets at least one line,
  and the first line of each section is priority 1: a listener must hear when the piece changes (into floorwork,
  into a chorus, into pairs).
- Group structure is priority 1: unison, a canon (the same move rippling through dancers one after another: say it
  is a canon and which way it travels), a soloist breaking out, pairs forming, formation changes.
- Name the technique, not a mime: sharp geometric hand and arm shapes are tutting even when they suggest an image;
  say the technique, and the image only as a comparison ("tutting, hands framing a crown"). The same goes for
  waacking, voguing, popping, locking, krump and floorwork.
- In arm-driven choreography (commercial, waacking, tutting, vogue hands, much contemporary) the arms are the
  content: say the arms' path and dynamics, not just the step: sliced, flicked, snapped, whipped, wrapped, staccato
  hits or a sustained reach, and where they land (framing the face, across the chest, overhead). Convey sharpness
  with callouts on the accents ("Slice! Flick! Wrap the face!") rather than a summary line.
- Fusion: when a piece draws on several styles, pick out each influence as it appears and use that style's own
  technical language for those moments (popping hits, a Bharatanatyam mudra, a contemporary release into the floor,
  a vogue duckwalk), and say when the piece shifts from one influence to another.
- Choose the moments that matter; never repeat a description. Present tense. Only describe what you can see; if
  unsure of a term, describe the shape plainly.

How and when to say it: the music is the star, the description is tasteful commentary inside it.
- Lead with the step's name whenever the style has one: the name carries the most in the fewest words
  ("Glissade, then a sissonne, legs split wide." not "Glides left, springs up"; "Cambré, arching back." not
  "Arches back"). Every recognisable step gets its name. Add a few plain words only where they help picture it.
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
line (scene and starting position), the first line of each section, canons or formation changes, and the piece's
signature: whatever makes this choreography distinctive (intricate, sharp arm work; a recurring motif). Most other
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

REVISE = """These lines from your audio description script contradict the pose measurements for the moments they
describe. Revise each so it only says what is consistent with the measurement, keeping its expressiveness and
length, or return null for it if you can't. Return JSON: {"lines": [{"time": t, "text": "..." or null}]}.

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


def structure_notes(plan: dict) -> str:
    """The director's performance map as text: sections with formation, group structure and techniques; motifs."""
    out = [f"Structure of the piece (style: {plan['style']['name']}):"]
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
    prompt += clip_note(start, end)
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
