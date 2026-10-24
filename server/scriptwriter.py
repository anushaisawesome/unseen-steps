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

BRIEF = """You are an expert audio describer for dance, and a former dancer in this style. Describe this performance
for a blind listener who loves dance, the way a dancer would see it: as rich and precise as a dancer would be, in few
words, spoken over the music.

A dancer's eye picks up:
- what this piece is (the style and, if you recognise it, the work, the variation or the character) and what the
  dancer is portraying;
- the quality and intention behind each movement, not just the movement: attack, ease, playfulness, control, weight,
  what a jump or an extension expresses;
- the detail that makes it impressive or beautiful: the height and placement of an extension, the speed and finish of
  turns, the shape of the body in a hold or a freeze, the arms and hands, the head, hair and face, the feet and
  footwork, the use of a prop, where the gaze goes;
- how the movement plays with the music: accents, suspensions, a step landing on a beat, a change of texture or
  energy as it happens;
- for groups: formations, unison, canon, who stands out.
Use the style's own terms where they fit, only when every part of the term's definition is visible, and let a
newcomer picture each term the first time. Directions as the audience sees them. Only describe what you can see, at
the moment it happens.

How to say it: one idea per line, never a list of details; most lines 5 to 12 words. At most one line per musical
phrase (phrase starts are listed below when there's a beat grid; otherwise listen for them), placed in the gap where
the phrase starts, plus brief callouts on standout hits. Leave the music room. time is when the line starts, just
after the movement it describes. delivery is a short tone note for the voice, never slow.

For each line give: time, moment_start and moment_end (the movement it describes), who (solo, pair, group or
subgroup), kind (description or callout), pace (steady, brisk or rapid), delivery, and text."""

SCHEMA = {
    "type": "object",
    "properties": {
        "style": {"type": "string"},
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "time": {"type": "number"}, "moment_start": {"type": "number"}, "moment_end": {"type": "number"},
            "who": {"type": "string", "enum": ["solo", "pair", "group", "subgroup"]},
            "kind": {"type": "string", "enum": ["description", "callout"]},
            "pace": {"type": "string", "enum": list(RATE)},
            "delivery": {"type": "string"}, "text": {"type": "string"}},
            "required": ["time", "moment_start", "moment_end", "who", "kind", "pace", "delivery", "text"]}},
    },
    "required": ["style", "lines"],
}

REVIEW = """You are a second expert dance describer, and a former dancer in this style, reviewing a colleague's audio
description script against the video (watch and listen closely). Their map of the piece and the script are below.

Read it as a dancer would hear it. Does it say what a dancer sees: what the piece is and what the dancer portrays, the
quality and intention behind the movement (what a jump or an extension expresses, not just that it happened), the
detail that makes it impressive, how it plays with the music, the moments that matter most? Is every line accurate and
at the right time (the right movement, prop, technique term and speed)? Is it one idea per line, with room for the
music (at most one line per musical phrase plus brief callouts on standout hits)? Replace flat or wrong lines with
what a dancer would say, add what a dancer would miss, drop what is surplus. Its measured density is below.

Return JSON {"notes": "one or two sentences on what was missing or wrong", "edits": [...]}, each:
{"action": "replace", "time": t, "text": "...", ...} (the line starting nearest t),
{"action": "add", "time": t, "moment_start": s, "moment_end": e, "text": "...", ...},
{"action": "drop", "time": t}.
replace and add also give kind, pace, delivery and who, as in the script.

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
            f"Strongest hits (seconds): {hits}\n"
            f"Musical phrases start at (seconds): " + " ".join(f"{p[0]:.1f}" for p in song["phrases"]))


def structure_notes(plan: dict) -> str:
    """The director's performance map as text: sections with formation, group structure and techniques; motifs."""
    out = ["Signature of this piece (must come through):"]
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
        if sec.get("detail"):
            out.append(f"  Close look, second by second:\n  " + sec["detail"].replace("\n", "\n  "))
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


def review_script(video: str, script: dict, plan: dict | None, song: dict | None = None,
                  start: float | None = None, end: float | None = None, passes: int = 2) -> dict:
    """A second Argon pass watches the video with the script and fixes what a blind listener would miss. Cached."""
    listing = "\n".join(f"{l['time']:.1f} s [{l['kind']}, {l['pace']}] {l['text']}" for l in script["lines"])
    length = (song["beats"][-1] - song["beats"][0]) if song else (end - (start or 0)) if end else None
    spoken = sum(len(l["text"].split()) / RATE.get(l["pace"], 2.8) + 0.4 for l in script["lines"])
    density = (f"\nMeasured density: about {spoken:.0f} s of speech in {length:.0f} s ({spoken / length:.0%})."
               if length else "")
    prompt = (REVIEW + (structure_notes(plan) + "\n\n" if plan else "") + "Script:\n" + listing + density
              + clip_note(start, end))
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
    for edit in review.get("edits", []):
        near = min(lines, key=lambda l: abs(l["time"] - edit.get("time", 0)), default=None)
        if edit.get("action") in ("replace", "drop") and (near is None or abs(near["time"] - edit["time"]) > 1.5):
            continue
        if edit["action"] == "drop":
            lines.remove(near)
        elif edit["action"] == "replace" and edit.get("text"):
            near.update({k: v for k, v in edit.items() if k in ("text", "kind", "pace", "delivery", "who")},
                        reviewed=True)
        elif edit["action"] == "add" and edit.get("text"):
            t = edit["time"]
            lines.append({"time": t, "moment_start": edit.get("moment_start", t - 2), "moment_end": edit.get("moment_end", t),
                          "who": edit.get("who", "solo"), "kind": edit.get("kind", "description"),
                          "pace": edit.get("pace", "steady"), "delivery": edit.get("delivery", ""),
                          "text": edit["text"], "reviewed": True})
    lines = [l for l in lines if l.get("pace") in RATE] + [dict(l, pace="steady") for l in lines if l.get("pace") not in RATE]
    lines = keep_signature(script["lines"], lines, plan)
    lines = in_meter(lines, song["beats"]) if song else sorted(lines, key=lambda l: l["time"])
    reviewed = {**script, "lines": lines, "review": review.get("notes", "")}
    if length and passes > 1:  # still far too dense: one more editing pass, watching the video again
        spoken = sum(len(l["text"].split()) / RATE.get(l["pace"], 2.8) + 0.4 for l in lines)
        if spoken / length > 0.45:
            again = review_script(video, reviewed, plan, song, start, end, passes=passes - 1)
            again["review"] = reviewed["review"] + " " + again["review"]
            return again
    return reviewed


VERIFY = {"type": "object", "properties": {"accurate": {"type": "boolean"}, "issue": {"type": "string"},
          "fix": {"type": "string", "nullable": True}}, "required": ["accurate", "issue", "fix"]}


def verify_lines(video: str, lines: list[dict], start: float | None = None, end: float | None = None) -> list[dict]:
    """Check every line against the moment it's spoken, at 10 frames a second: the right movement, at the right time,
    the right technique, and nothing that isn't there. Wrong lines are corrected or dropped. The visual counterpart of
    the pose checker, so it works on any video and style (including YouTube links, which have no pose)."""
    from concurrent.futures import ThreadPoolExecutor

    def check_one(line):
        a = max(start or 0, min(line.get("moment_start", line["time"] - 3), line["time"] - 3))
        b = min(line["time"] + 1.5, end) if end else line["time"] + 1.5
        prompt = (f"An audio describer says this at {line['time']:.1f} s in the video: \"{line['text']}\"\n"
                  f"It should describe what happens between {a:.1f} s and {line['time'] + 1:.1f} s (the clip shown). "
                  "Is it accurate: the right movement, at this time, the right technique or style term, the right "
                  "speed and dynamics, and nothing that isn't there? If not, give a corrected line of about the same "
                  "length that is accurate for this moment, or null to drop it.")
        try:
            r = with_retry(lambda: client().models.generate_content(
                model=MODEL, contents=[video_part(video, a, b, fps=10), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=VERIFY,
                                                   thinking_config=types.ThinkingConfig(thinking_level="low"))))
            return json.loads(r.text)
        except Exception:
            return {"accurate": True, "issue": "unchecked", "fix": None}

    with ThreadPoolExecutor(max_workers=6) as pool:
        verdicts = list(pool.map(check_one, lines))
    out = []
    for line, v in zip(lines, verdicts):
        if v["accurate"]:
            out.append(dict(line, verified="yes"))
        elif v.get("fix"):
            print(f"   seen wrong at {line['time']:.1f}s: \"{line['text']}\" ({v['issue'][:80]}) -> \"{v['fix']}\"")
            out.append(dict(line, text=v["fix"], verified="corrected", was=line["text"], issue=v["issue"]))
        else:
            print(f"   seen wrong at {line['time']:.1f}s, dropped: \"{line['text']}\" ({v['issue'][:80]})")
    return out


KEEP = {"type": "object", "properties": {"restore": {"type": "array", "items": {"type": "integer"}}},
        "required": ["restore"]}


def keep_signature(before: list[dict], after: list[dict], plan: dict | None) -> list[dict]:
    """Editing for density must never erase the piece's signature (on Track 10 it deleted nearly every line about the
    arm work). Compare the edited script with the original, quality by quality from the map's signature, and restore
    the original lines that carried a quality the edit lost or thinned out."""
    if not plan or not plan.get("signature") or not before:
        return after
    qualities = "\n".join(f"- {q['quality']} ({q['body']})" for q in plan["signature"])
    original = "\n".join(f"{n}. {l['time']:.1f} s: {l['text']}" for n, l in enumerate(before))
    edited = "\n".join(f"{l['time']:.1f} s: {l['text']}" for l in after)
    prompt = (f"The signature of this dance piece:\n{qualities}\n\nOriginal script (numbered):\n{original}\n\n"
              f"Edited script:\n{edited}\n\nFor each signature quality: is it still in the edited script at all? Only "
              "where a quality has disappeared completely, give the number of the one original line that best restores "
              "it (at most 2 in total). "
              "Return JSON {\"restore\": [numbers]} (empty if nothing was lost).")
    response = with_retry(lambda: client().models.generate_content(
        model="gemini-3.8-flash", contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=KEEP,
                                           thinking_config=types.ThinkingConfig(thinking_level="low"))))
    restore = [before[n] for n in json.loads(response.text)["restore"] if 0 <= n < len(before)]
    times = {round(l["time"], 1) for l in after}
    back = [dict(l, restored=True) for l in restore if round(l["time"], 1) not in times]
    if back:
        print(f"   signature guard restored: {[l['text'] for l in back]}")
    return sorted(after + back, key=lambda l: l["time"])


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
