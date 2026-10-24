"""Check a drafted line against the measured movement before it's spoken.

Each rule ties words in the line to a measurement. A line that claims something
the measurements don't support is rejected with a reason the writer can fix.
"""

import re
from dataclasses import dataclass

MAX_WORDS = 14

# word stems -> (the measurement it needs, what must be true of the features, reason if it isn't).
# If that measurement wasn't taken (None, e.g. jumps in a crowd), the claim is left unchecked.
CLAIMS = [
    # jumps, including ballet jumps by name
    (r"\b(jump|leap|hop|spring|bound|soar|vault)\w*|\b(jet[eé]s?|sissonnes?|soubresauts?|entrechats?|cabrioles?|"
     r"assembl[eé]s?|saut[eé]s?|changements?|tour en l'air)\b|\b(in the air|mid-air|airborne)\b|\b(lifts?|hoists?)\s+(her|him|them|his partner|her partner|a dancer|the ballerina)\b(?!\s+(arm|hand|leg|head|chin|gaze))",
     "max_rise", lambda f: (f.get("max_rise") or 0) >= 0.05,
     "it mentions a jump or lift, but no rise was measured"),
    (r"\b(?!turn(ed|s)?[ -]?out)(spin|turn|pirouette|rotat|twirl|whirl|fouett|ch[aâî]+n[eé]|pivot)\w*",
     # a change of facing ("turns to face the front") is a turn too
     "turns", lambda f: (f.get("turns") or 0) >= 1 or any("now " in e for e in (f.get("events") or [])),
     "it mentions turning, but no turn was measured"),
    (r"\b((to|on|onto) the floor|floor ?work|kneel\w*|crouch\w*|roll\w*|sink\w*|low)\b",
     "lowest_level", lambda f: f.get("lowest_level") in ("floor", "low"),
     "it mentions going low or to the floor, but the dancer stayed standing"),
    # "still" only as stopping ("stands still"), not as "continuing" ("still facing us")
    (r"\b(stands?|holds?|stays?|remains?|keeps?)\s+still\b|\b(stillness|paus\w*|freez\w*|frozen|motionless|rests?|resting)\b",
     "stillness", lambda f: (f.get("stillness") or 0) >= 0.3,
     "it mentions stillness, but the dancer kept moving"),
    (r"\b(kick(s|ed|ing)?|battements?|high leg|leg (swings?|flicks?) (up|high))\b",
     "events", lambda f: any("kick" in e or "high leg" in e for e in (f.get("events") or [])),
     "it mentions a kick or high leg, but none was measured"),
]

INDIVIDUAL = r"\b(she|he|her|his|him|the leader|the follower|one dancer|the other)\b"


@dataclass
class Verdict:
    passed: bool
    reason: str | None = None


def check(line: str, features: dict, max_words: int = MAX_WORDS) -> Verdict:
    text = line.lower()

    words = len(re.findall(r"[a-z']+", text))
    if words > max_words:
        return Verdict(False, f"it is {words} words; the limit is {max_words}")

    for pattern, needs, supported, reason in CLAIMS:
        if needs in features and features[needs] is None:
            continue
        if re.search(pattern, text) and not supported(features):
            return Verdict(False, reason)

    travel = features.get("travel")
    for side in () if features.get("travel", "") is None else ("left", "right"):
        # A turn's side is the dancer's rotation ("turns left", "turns to his right"): check it against rotation.
        rotating = (rf"\b(turn|spin|pivot|rotat|circl|twirl|whirl)\w*\s+(to\s+)?((his|her|their|the)\s+)?{side}\b"
                    rf"(?!\s+(arm|hand|leg|foot|shoulder|hip|knee|elbow))")
        if re.search(rotating, text) and features.get("rotation") != side:
            measured = features.get("rotation") or "no clear direction"
            return Verdict(False, f"it says the turn goes to the {side}, but the measured rotation was {measured}")
        # Facing, pointing or profile isn't travel either.
        facing = (rf"\b(fac\w*|point\w*|look\w*)\s+(to\s+(the\s+)?)?{side}\b|\bprofile\s+(to\s+the\s+)?{side}\b"
                  rf"|\bside-on[^.,;]*\b{side}\b")
        rest = re.sub(facing, " ", re.sub(rotating, " ", text))
        moving = rf"\b{side}(ward)?s?\b(?!\s+(arm|hand|leg|foot|shoulder|hip|knee|elbow|side))"
        if re.search(moving, rest) and travel != side:
            measured = travel if travel in ("left", "right") else "no clear direction"
            return Verdict(False, f"it says {side}, but the measured travel was {measured}")

    # Telling two partners apart needs good tracking; in a group, lines are about the group or a soloist.
    if features.get("people") == 2 and features.get("tracking") != "good" \
            and re.search(INDIVIDUAL, text):
        return Verdict(False, "it describes one dancer, but the two dancers aren't tracked well enough to tell apart")

    return Verdict(True)
