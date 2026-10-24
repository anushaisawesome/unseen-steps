"""Retry Gemini calls that fail because of rate limits (429) or an overloaded model (503).

The hackathon accounts have per-minute limits and new models are often busy, so a short wait
and another try usually works. Anything else (a bad request, an exhausted spending cap) fails
straight away.
"""

import time

from google.genai import errors


def with_retry(call, attempts: int = 4, wait: float = 4.0):
    """Run call(), retrying up to `attempts` times with a growing wait on 429 and 503 errors."""
    for attempt in range(attempts):
        try:
            return call()
        except errors.APIError as e:
            spending_cap = "spending cap" in str(e).lower()
            if e.code not in (429, 503) or spending_cap or attempt == attempts - 1:
                raise
            time.sleep(wait * (2 ** attempt))
