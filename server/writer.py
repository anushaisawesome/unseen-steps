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
MAX_WORDS = 8

SYSTEM = f"""You are a live audio describer for dance. A blind audience member hears you through earphones, in a short gap between musical phrases.

Describe what the dancers did in the phrase that just ended.
- Use only the measured movement you are given, including its timeline of events, and the close-up images of the dancers if there are any. Never describe a movement the measurements contradict.
- Pick the most striking moment of the phrase (a spin, a kick, an arm flourish, a break-apart) rather than summarising everything.
- At most {MAX_WORDS} words, present tense, said the way a person would say it aloud.
- Be concrete: direction as the audience sees it (say "to the left" or "to the right", never "stage left" or "stage right", which mean the opposite to a listener), level (high, low, on the floor), and quality (sharp, flowing, sweeping, still).
- Use a dance term only if it appears in the matching terms you are given. Otherwise describe the shape plainly.
- With two dancers, describe the couple together unless tracking is "good".
- Never describe the music, and never guess feelings or costumes unless the show notes mention them. Say "in hold", never "embrace".
- Don't repeat the wording of previous lines.
- Only stay silent (line null) when tracking is "poor" or the phrase is a plain repeat of the previous one. Otherwise always describe something."""

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
        sections.append("Previous lines:\n" + "\n".join(f"- {line}" for line in previous[-3:]))
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
