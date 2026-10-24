"""Write one spoken line about the dance phrase that just ended.

Usage (try it on sample features):
    python server/writer.py data/samples/features.json
"""

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
except ImportError:  # Running as ``python server/writer.py``.
    from settings import gemini_api_key

MODEL = "gemini-3.8-flash"
MAX_WORDS = 12

SYSTEM = f"""You are an experienced audio describer for dance. A blind audience member hears you through earphones, in a short gap in the music, about the phrase of dance that just ended. Describe it the way a skilled human describer would: knowledgeable about the style, selective, vivid, never repetitive.

What to say:
- What matters to understanding the dance: the step or figure, its shape and quality (smooth, sweeping, lilting, sharp, held), where the dancer faces and travels, and how the pattern develops.
- Use the show notes from the director, who has watched the whole performance: name the section, recognise a recurring motif ("the box again, now with his back to us"), and use what they say the movement is (for example a raised arm held in a ballroom frame is the frame for an imaginary partner, not "pointing up").
- Use the style's vocabulary when the matching terms or the measured footwork support it, and the first time you use a term, add a few words that let a newcomer picture it ("a box step, his feet tracing a square").
- Orientation matters: when the facing changes, say so ("now with his back to us", "turning side-on to face left").
- Connect to the music when it helps: in waltz, the rise and fall over each bar of three.

What not to say:
- Never repeat something already said in the previous lines. If the dancer repeats a pattern, say what changed (direction, facing, size, speed) or stay silent (line null).
- Don't narrate incidental gestures (touching headphones, fidgeting) or the obvious ("he is dancing").
- Don't start every line with "He"; vary the openings.
- Use only movement the measurements and notes support; never invent.
- Directions: travel as the audience sees it ("moves to the left"; never "stage left"); turns by the dancer's own side from the measured rotation ("turns to his right"); if rotation is missing or mixed, just "turns".
- Never describe the music itself, or guess feelings or costume beyond the notes.
- With two dancers, describe the couple together unless tracking is "good". Say "in hold", never "embrace".

At most {MAX_WORDS} words, present tense, natural spoken English. Stay silent (line null) when tracking is "poor" or the phrase adds nothing new."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"line": {"type": "string", "nullable": True}},
    "required": ["line"],
}

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=gemini_api_key())
    return _client


def build_prompt(features: dict, previous: list[str], notes: str, vocab: list[str],
                 feedback: str | None) -> str:
    sections = ["Measured movement for the phrase that just ended:\n" + json.dumps(features, indent=1)]
    if previous:
        sections.append("Previous lines (don't repeat them):\n" + "\n".join(f"- {line}" for line in previous[-5:]))
    if notes:
        sections.append("Show notes:\n" + notes)
    if vocab:
        sections.append("Matching dance terms: " + ", ".join(vocab))
    if feedback:
        sections.append(f"Your last draft was rejected: {feedback}. Write a new line that fixes this.")
    return "\n\n".join(sections)


def write_line(features: dict, previous: list[str] = (), notes: str = "", vocab: list[str] = (),
               frames: list[bytes] = (), feedback: str | None = None) -> str | None:
    """Return one line to speak, or None when it's better to stay silent."""
    contents = [build_prompt(features, list(previous), notes, list(vocab), feedback)]
    contents += [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg") for jpeg in frames]
    response = with_retry(lambda: client().models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    ))
    line = (json.loads(response.text or "{}").get("line") or "").strip()
    return line or None


def main():
    samples = json.loads(Path(sys.argv[1]).read_text())
    previous = []
    for sample in samples:
        start = time.perf_counter()
        line = write_line(sample["features"], previous, vocab=sample.get("vocab", []))
        took = time.perf_counter() - start
        print(f"[{sample['label']}] {took:.1f}s  ->  {line or '(silent)'}")
        if line:
            previous.append(line)


if __name__ == "__main__":
    main()
