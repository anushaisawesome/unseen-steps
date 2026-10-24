# Copied from server/settings.py by scripts/web_sync_server.py: edit the original.
"""Project environment settings.

The documented variable names are preferred. A few legacy aliases are accepted so a
local .env can be used without rewriting it; never log returned values.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def first_env(*names: str) -> str | None:
    """Return the first non-empty environment value from ``names``."""
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def gemini_api_key() -> str:
    key = first_env("GEMINI_API_KEY", "GOOGLE_API_KEY", "Google_Gemini_API_Key")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY in .env")
    return key


def mongodb_uri() -> str | None:
    return first_env("MONGODB_URI", "MongoDB_URI")


def mongodb_user() -> str | None:
    return first_env("MONGODB_USER", "MONGODB_USERNAME")
