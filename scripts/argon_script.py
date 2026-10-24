"""Experiment: Argon as the describer. Watches a whole video (file or public YouTube link, which Gemini reads
itself; we never download YouTube) and writes a timed audio description script.

Usage: python scripts/argon_script.py clips/ballet.mp4 out.json
"""
import json, sys, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "server"))
from google.genai import types
from director import client
from retry import with_retry

BRIEF = """You are an expert audio describer for dance, writing the audio description script for blind and partially
sighted audience members. A skilled human describer prepares this from a recording, then it is delivered live,
in the gaps of the music. Write the script for this video.

Write like the best dance describers:
- Name what the dancer actually does in the style's own vocabulary, accurately (ballet: positions such as fifth,
  steps such as glissade, sissonne, grand jeté, pas de bourrée, pirouette, port de bras, arabesque, épaulement;
  ballroom: frame, rise and fall, box, natural/reverse turn, and so on). The first time a term appears, add a few
  plain words so a newcomer can picture it ("a grand jeté, a split leap through the air").
- Capture quality, dynamics and expression, not just mechanics: weight (light, grounded), time (sudden,
  sustained), flow (free, bound), the shape of the body and line, where the gaze goes, and the feeling the
  movement gives (playful, yearning, triumphant). Ground feeling in what is visible.
- Say where dancers are and how they relate: facing, travel across the space, and for groups the formation
  (lines, circles, diagonals), unison or canon, a soloist breaking out, pairs forming and travelling.
- Choose moments of significance; skip the trivial and never repeat. Short, vivid, present tense.
- Lines are spoken over the music, so keep each one short enough to say in a few seconds (about 8 to 16 words),
  and time each line at the moment it should start, just after the movement it describes.
- Only describe what you can see. If unsure of a term, describe the shape plainly instead.

Return JSON: {"style": "...", "lines": [{"time": seconds, "text": "...", "terms": ["..."]}]}."""

source = sys.argv[1]
if source.startswith("http"):
    video = types.Part(file_data=types.FileData(file_uri=source))
else:
    video = client().files.upload(file=source)
    while video.state.name == "PROCESSING":
        time.sleep(2); video = client().files.get(name=video.name)
t = time.perf_counter()
r = with_retry(lambda: client().models.generate_content(
    model="gemini-4-argon", contents=[video, BRIEF],
    config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="high"),
                                       response_mime_type="application/json")))
print(f"[{time.perf_counter() - t:.0f}s]")
out = json.loads(r.text)
print("style:", out.get("style"))
for l in out["lines"]:
    print(f"{l['time']:6.1f}s  {l['text']}")
json.dump(out, open(sys.argv[2], "w"), indent=2, ensure_ascii=False)
