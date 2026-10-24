"""Check a drafted line against the measured movement before it's spoken.

Each rule ties words in the line to a measurement. A line that claims something
the measurements don't support is rejected with a reason the writer can fix.
"""

import re
from dataclasses import dataclass

MAX_WORDS = 10

# word stems -> (what must be true of the features, reason if it isn't)
CLAIMS = [
    (r"\b(jump|leap|hop|spring|bound)\w*|\blift\w*\b(?!\s+(his|her|their|one|an|the|both)\s+(arm|hand|leg|head|chin))",
     lambda f: (f.get("max_rise") or 0) >= 0.05,
     "it mentions a jump or lift, but no rise was measured"),
    (r"\b(spin|turn|pirouette|rotat|twirl|whirl)\w*",
     lambda f: (f.get("turns") or 0) >= 1,
     "it mentions turning, but no turn was measured"),
    (r"\b((to|on|onto) the floor|floor ?work|kneel|crouch|roll|sink|low)\w*",
     lambda f: f.get("lowest_level") in ("floor", "low"),
     "it mentions going low or to the floor, but the dancer stayed standing"),
    (r"\b(still|stillness|pause|freez|frozen|motionless|rest)\w*",
     lambda f: (f.get("stillness") or 0) >= 0.3,
     "it mentions stillness, but the dancer kept moving"),
]

INDIVIDUAL = r"\b(she|he|her|his|him|the leader|the follower|one dancer|the other)\b"


@dataclass
class Verdict:
    passed: bool
    reason: str | None = None


def check(line: str, features: dict) -> Verdict:
    text = line.lower()

    words = len(re.findall(r"[a-z']+", text))
    if words > MAX_WORDS:
        return Verdict(False, f"it is {words} words; the limit is {MAX_WORDS}")

    for pattern, supported, reason in CLAIMS:
        if re.search(pattern, text) and not supported(features):
            return Verdict(False, reason)

    travel = features.get("travel")
    for side in ("left", "right"):
        # "left"/"right" as a direction of travel, not a body part ("his right arm").
        moving = rf"\b{side}(ward)?\b(?!\s+(arm|hand|leg|foot|shoulder|hip|knee|elbow|side))"
        facing = rf"\b(fac\w*|point\w*|look\w*)\s+(to\s+(the\s+)?)?{side}\b"  # facing/pointing isn't travel
        if re.search(moving, text) and not re.search(facing, text) and travel != side:
            measured = travel if travel in ("left", "right") else "no clear direction"
            return Verdict(False, f"it says {side}, but the measured travel was {measured}")

    if (features.get("people") or 1) > 1 and features.get("tracking") != "good" \
            and re.search(INDIVIDUAL, text):
        return Verdict(False, "it describes one dancer, but the two dancers aren't tracked well enough to tell apart")

    return Verdict(True)
