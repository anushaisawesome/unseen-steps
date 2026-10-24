"""Put a checked English line into the listener's language, using dancers' own terms.

The line is checked in English first (see checker.py), so translation can't add a claim the
movement doesn't support. The glossary comes from the vocabulary collection: each term's name
in each language, as dancers actually say it (found with Deep Research, not machine translation).

Usage:
    python server/localise.py de "The couple turns together, drifting to the right."
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL = "gemini-3.8-flash"
LANGUAGES = {"en": "English", "uk": "Ukrainian", "de": "German", "hi": "Hindi"}

SYSTEM = """You translate live audio description of dance for blind audience members.
- Keep exactly the same meaning. Add nothing and drop nothing.
- Say it the way a native speaker would say it aloud, short and natural, not word for word.
- Where a glossary term fits, use the glossary's name for it in the target language. Never invent a technical term.
- Keep it as short as the English, because it has to fit in a gap in the music."""

SCHEMA = {"type": "object", "properties": {"line": {"type": "string"}}, "required": ["line"]}

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def localise(line: str, lang: str, glossary: dict[str, str] | None = None) -> str:
    """glossary maps English terms to their names in `lang`, e.g. {"natural turn": "Rechtsdrehung"}."""
    if lang == "en":
        return line
    prompt = f"Translate into {LANGUAGES.get(lang, lang)}:\n{line}"
    if glossary:
        prompt += "\n\nGlossary (English: target language):\n" + "\n".join(f"- {en}: {term}" for en, term in glossary.items())
    response = client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            response_mime_type="application/json",
            response_schema=SCHEMA,
        ),
    )
    return json.loads(response.text)["line"].strip()


if __name__ == "__main__":
    print(localise(sys.argv[2], sys.argv[1]))
