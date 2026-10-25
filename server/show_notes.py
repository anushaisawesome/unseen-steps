"""Show notes: what Argon prepares from a studio's rehearsal video so the live narration knows the piece.

The notes hold the style, the dancer's signature, the sections with their formations and techniques, every change of
texture and energy, the key moments with their song times, and the vocabulary; the song analysis adds the gaps where
narration fits. Live, Gemini Live starts with these notes and describes what the dancer actually does in each gap.
"""

try:
    from .director import performance_map
    from .scriptwriter import key_moments, structure_notes
except ImportError:
    from director import performance_map
    from scriptwriter import key_moments, structure_notes


def prepare(rehearsal: str, style: str | None = None) -> tuple[dict, list[tuple[float, str]], str]:
    """(the map, the key moments, the notes as text). Cached per video, so preparing twice is instant."""
    print("preparing show notes from the rehearsal video (cached after the first time)...")
    plan = performance_map(rehearsal, style_hint=style)
    moments = key_moments(plan)
    notes = (structure_notes(plan) + "\nKey moments in rehearsal (song time): "
             + "; ".join(f"{t:.0f} s {what}" for t, what in moments))
    return plan, moments, notes
