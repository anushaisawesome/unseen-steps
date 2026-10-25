"""Show notes: what Argon prepares from a studio's rehearsal video so the live narration knows the piece.

The notes hold the style, the dancer's signature, the sections with their formations and techniques, every change of
texture and energy, the key moments with their song times, and the vocabulary; the song analysis adds the gaps where
narration fits. Live, Gemini Live starts with these notes and describes what the dancer actually does in each gap.
"""

try:
    from .director import client, performance_map
    from .scriptwriter import key_moments, structure_notes, verify_lines, write_script_windowed
except ImportError:
    from director import client, performance_map
    from scriptwriter import key_moments, structure_notes, verify_lines, write_script_windowed


def prepare(rehearsal: str, style: str | None = None, song: dict | None = None
            ) -> tuple[dict, list[tuple[float, str]], str, list[dict]]:
    """(the map, the key moments, the notes as text, the rehearsal script). Cached per video, so preparing twice is
    instant. The script is the tuned describer's (the dancer's-eye writer, every line checked against the rehearsal
    video, not voiced): live, each prompt carries the rehearsal line for that moment as the quality of language to
    match, while Gemini Live describes what the dancer actually does tonight."""
    print("preparing show notes from the rehearsal video (cached after the first time)...")
    client()  # create the Gemini client before the writer's threads (created lazily inside them, it raced)
    plan = performance_map(rehearsal, style_hint=style)
    moments = key_moments(plan)
    notes = (structure_notes(plan) + "\nKey moments in rehearsal (song time): "
             + "; ".join(f"{t:.0f} s {what}" for t, what in moments))
    lines = write_script_windowed(rehearsal, song, style_hint=style, plan=plan)["lines"]
    lines = verify_lines(rehearsal, lines, plan=plan)
    script = [{"time": round(float(l["time"]), 2), "text": l["text"]} for l in sorted(lines, key=lambda l: l["time"])]
    return plan, moments, notes, script
