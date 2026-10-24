"""Regression check: does the narration still do everything Anusha's feedback asked for?

Each video has must-haves taken from her reviews (in her words where possible). After any change to the describer,
re-render, then run this: Gemini Flash reads each timed script and judges every must-have, and two things are
measured directly (longest silence, longest line). A fix for one video can't quietly break another.

Usage:
    python scripts/regress.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from google.genai import types  # noqa: E402
from director import client  # noqa: E402
from retry import with_retry  # noqa: E402

# From feedback/*.md: what a dancer said was missing or wrong.
MUST = {
    "ponyboy": ["describes the canon: the dancers doing the same move one after another"],
    "track10": ["describes the arm work (the main element of this choreography) in detail",
                "conveys the sharpness of the movement",
                "conveys the texture change from sharp to fluid for the build-up, around 12 s",
                "calls the clap and the turn round just before the vocals come in",
                "describes the groove at the end with rich, specific detail",
                "opens with a line that gives context (who is dancing, how they start)"],
    "arcamarine": ["describes the texture of the movement (e.g. sinuous, sharp, heavy), not just the steps",
                   "describes poses: the shape the body makes at holds and hits"],
    "judas": ["describes a canon (the same move rippling through dancers one after another)",
              "names tutting as tutting, not as miming an object such as crowns",
              "describes the floorwork section (about 90-122 s)"],
    "ballet": ["opens with the starting position: fifth position",
               "names the ballet steps with their terms (e.g. glissade, sissonne, soubresaut, jeté)"],
}
SILENCE = 8.0   # seconds of quiet while the piece goes on
LONGEST = 10    # words in a single line

JUDGE = {"type": "object", "properties": {"pass": {"type": "boolean"}, "evidence": {"type": "string"}},
         "required": ["pass", "evidence"]}


def scripts() -> dict:
    """Spoken lines per video key: [(time, seconds, text)], from the YouTube demos and the local renders."""
    out = {}
    demo = ROOT / "web/youtube-demo/data.json"
    if demo.exists():
        for d in json.loads(demo.read_text()):
            out[d["key"]] = [(l["at"], l["seconds"], l["text"]) for l in d["lines"] if l.get("audio")]
    for key in ("judas", "ballet", "andrii720"):
        f = ROOT / f"data/killtest/{key}-script.json"
        if f.exists():
            out[key] = [(r["speech"]["at"], r["speech"]["seconds"], r["line"]) for r in json.loads(f.read_text())
                        if r.get("speech")]
    return out


def judge(must: str, lines: list) -> dict:
    listing = "\n".join(f"{t:.1f} s: {text}" for t, _, text in lines)
    prompt = (f"Here is the timed audio description of a dance (what a blind listener hears):\n{listing}\n\n"
              f"Does it meet this requirement? \"{must}\"\nJudge strictly from the lines; quote the line(s) that "
              "meet it as evidence, or say what's missing.")
    r = with_retry(lambda: client().models.generate_content(
        model="gemini-3.8-flash", contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=JUDGE,
                                           thinking_config=types.ThinkingConfig(thinking_level="low"))))
    return json.loads(r.text)


def main():
    found = scripts()
    passed = total = 0
    for key, lines in found.items():
        if not lines:
            continue
        gaps = [b[0] - (a[0] + a[1]) for a, b in zip(lines, lines[1:])]
        longest_gap = max(gaps, default=0)
        longest_line = max(len(t.split()) for _, _, t in lines)
        print(f"\n{key}: {len(lines)} lines · longest silence {longest_gap:.1f} s"
              f"{'  <-- too long' if longest_gap > SILENCE else ''} · longest line {longest_line} words"
              f"{'  <-- too long' if longest_line > LONGEST else ''}")
        for must in MUST.get(key, []):
            v = judge(must, lines)
            total += 1
            passed += v["pass"]
            print(f"   {'PASS' if v['pass'] else 'FAIL'}  {must}\n         {v['evidence'][:160]}")
    print(f"\n{passed}/{total} must-haves met")


if __name__ == "__main__":
    main()
