"""Narration demos for public YouTube videos, without downloading them.

Gemini reads a public YouTube link directly, so Argon can map the piece and write the script from the link.
Each line is voiced (checked against its caption, trimmed, fitted to time) and the page in web/youtube-demo/
plays the narration in sync with YouTube's own embedded player. There's no pose tracking (no video file), so
these lines are not checked against measured movement; the page says so.

Usage:
    python scripts/youtube_demo.py              # every video in VIDEOS (cached Argon work is reused)
    python scripts/youtube_demo.py arcamarine   # just one, by key
    cd web/youtube-demo && python -m http.server 8765   # then open http://localhost:8765
"""

import hashlib
import json
import subprocess
import sys
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from director import performance_map  # noqa: E402
from scriptwriter import (RATE, budget, review_script, revise, select_lines, verify_lines,  # noqa: E402
                          write_script, write_script_windowed)
from speech import speak  # noqa: E402

OUT = ROOT / "web" / "youtube-demo"
WINDOWED = "--whole" not in sys.argv  # write one short stretch at a time (--whole: the old one-pass writer)

# key, YouTube id, label, style hint, clip start and end (seconds)
VIDEOS = [
    ("arcamarine", "cRil1jtScjI", "Aquamarine, Paris Cavanagh choreography", "commercial / contemporary, leaning contemporary", 0, 63),
    ("track10", "HA22LboHCww", "Track 10, Paris Cavanagh choreography", "commercial / contemporary, leaning contemporary", 0, 41),
    ("ponyboy", "8qm6Pn9kYas", "Ponyboy, Isaiah Southall choreography", "commercial", 0, 24),
    ("vogue-battle", "Jhhd_tEaJEQ", "Streetstar 2013 vogue femme final: Lasseindra vs Inxi", "vogue femme battle", 84, 264),
    ("inxi-solo", "ksRh4fxTLOs", "Streetstar 2013, Inxi: Sailor Moon vogue solo", "vogue femme", 0, 63),
    ("leiomy", "pm9emJoXvH0", "Streetstar 2013, Leiomy: vogue femme solo", "vogue femme", 0, 101),
    ("saumya", "4fzJBU7HRno", "Saumya, Red Bull Dance Your Style 2024", "fusion: identify each style influence", 0, 180),
    ("ballet", "-yL2X-jkmCk", "Prix de Lausanne 2026, Dayeon Yeom: classical variation", "ballet", 0, 133),
    ("contemporary", "rY9PDSfEjUk", "Prix de Lausanne 2023, Ana Luisa Negrão: contemporary", "contemporary", 0, 159),
    ("waacking", "7StkcBL1jp4", "Red Bull Dance Your Style 2025: Hirokoboogie vs Waackxxxy", "waacking battle", 0, 180),
    ("tutting", "oJ6mC4DsOM4", "Sadeck: Murmuration (tutting)", "tutting", 0, 50),
    ("bharatanatyam", "TdYWOr12ONU", "IndianRaga: Vahana Alarippu", "Bharatanatyam", 0, 180),
    ("flamenco", "9JhUBiJPHMM", "Rocío Garrido: soleá", "flamenco", 0, 180),
    ("amapiano", "GQjf74DJjEc", "CPC Stars: amapiano", "amapiano", 0, 180),
    ("afrobeats", "uWqCqv6pmmU", "HomeBros: Afro dance choreography", "afrobeats", 0, 164),
    ("ballroom", "0GHkCRM8DBc", "WDSF World Open Prague: Standard final, waltz", "ballroom waltz", 0, 141),
]


def seconds(path: Path) -> float:
    with wave.open(str(path)) as f:
        return f.getnframes() / f.getframerate()


def build(video: tuple) -> dict:
    key, vid, label, style, start, end = video
    url = f"https://www.youtube.com/watch?v={vid}"
    plan = performance_map(url, style_hint=style, start=start, end=end)
    writer = write_script_windowed if WINDOWED else write_script
    script = writer(url, None, style_hint=style, plan=plan, start=start, end=end)
    script = review_script(url, script, plan, None, start, end)  # a second describer: what would a listener miss?
    script["lines"] = verify_lines(url, script["lines"], start, end)  # every line checked against its moment
    lines = [l for l in script["lines"] if start - 1 <= l["time"] <= end]
    if lines and max(l["time"] for l in lines) < start:  # times came back relative to the clip
        for l in lines:
            l["time"] += start
    # Lines longer than the time they have go back to Argon once to tighten; still too long means cut.
    limits = budget(lines, end)
    long = [{"time": l["time"], "text": l["text"], "reason": f"it is {len(l['text'].split())} words; the limit is {m}"}
            for l, m in zip(lines, limits) if len(l["text"].split()) > m]
    for when, text in revise(long).items():
        line = next((l for l in lines if abs(l["time"] - when) < 0.05), None)
        if line and text:
            line["text"] = text
    lines = [l for l, m in zip(lines, budget(lines, end)) if len(l["text"].split()) <= m + 1]
    audio = OUT / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    for n, line in enumerate(lines):
        until = lines[n + 1]["time"] if n + 1 < len(lines) else end
        target = len(line["text"].split()) / RATE.get(line["pace"], 2.8)
        fit = max(0.8, min(until - line["time"] - 0.2, target * 1.15))
        # Named by what it says, so a caption can never be paired with another script's audio.
        wav = audio / f"{key}-{hashlib.sha1(('v2' + line['text']).encode()).hexdigest()[:10]}.wav"
        mp3 = wav.with_suffix(".mp3")
        if not mp3.exists():  # a checked clip of exactly this line is reused
            try:
                speak(line["text"], wav, None, fit)
            except ValueError as e:
                print(f"   {e}; left out")
                line["status"], line["seconds"] = "voice failed", 0.0
                continue
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "64k",
                            str(mp3)], check=True)
            wav.unlink()
        line["seconds"] = round(float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
            capture_output=True, text=True, check=True).stdout), 2)
        line["audio"] = line["audio_kept"] = f"audio/{mp3.name}"
        line["at"] = line["time"]

    def share():
        return sum(l["seconds"] for l in lines if l.get("audio")) / (end - start)

    # The final cut: Argon, watching the video, keeps the lines a dancer would (the music stays the main thing).
    voiced = [l for l in lines if l.get("audio")]
    keep = select_lines(url, voiced, plan, end - start, start=start, end=end)
    for n, l in enumerate(voiced):
        if n not in keep:
            l["status"] = "left for the music"
            l.pop("audio")

    # No collisions, and no knock-on: a line that can't start within half a second of its moment is left out rather
    # than pushed later (pushing made every following line drift late).
    finish = 0.0
    for l in lines:
        if not l.get("audio"):
            continue
        if l["at"] < finish + 0.15:
            if finish + 0.15 - l["at"] > 0.5:
                l["status"] = "no room"
                l.pop("audio")
                continue
            l["at"] = round(finish + 0.15, 2)
        finish = l["at"] + l["seconds"]

    spoken = [l for l in lines if l.get("audio")]
    print(f"{key}: {plan['style']['name']}, {len(spoken)}/{len(lines)} lines spoken, speech {share():.0%}")
    return {"key": key, "id": vid, "label": label, "style": plan["style"]["name"], "start": start, "end": end,
            "review": script.get("review", ""),
            "signature": [f"{x['quality']}: {x['body']}" for x in plan.get("signature", [])],
            "sections": [{"start": s["start"], "end": s["end"], "label": s["label"], "group": s.get("group", "")}
                         for s in plan["sections"]],
            "lines": [{"at": l["at"], "text": l["text"], "kind": l["kind"], "pace": l["pace"],
                       "priority": l.get("priority"), "audio": l.get("audio"), "status": l.get("status", "spoken"),
                       "seconds": l["seconds"]} for l in lines]}  # audio_kept stays internal


def main():
    wanted = {a for a in sys.argv[1:] if not a.startswith("--")}
    videos = [v for v in VIDEOS if not wanted or v[0] in wanted]
    OUT.mkdir(parents=True, exist_ok=True)
    data_file = OUT / "data.json"
    existing = {d["key"]: d for d in json.loads(data_file.read_text())} if data_file.exists() else {}
    # Create each Gemini client once, before the threads: lazily created clients race, and the loser gets closed.
    import director
    import speech
    director.client(), speech.client()
    order = [v[0] for v in VIDEOS]

    def save():  # after every video, so the page fills in as the batch runs (refresh to see more)
        data = sorted(existing.values(), key=lambda d: order.index(d["key"]) if d["key"] in order else 99)
        data_file.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        (OUT / "data.js").write_text(
            "window.DEMOS = " + json.dumps(data, ensure_ascii=False) + ";\n")
        return data

    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(build_safely, v) for v in videos]):
            if result := future.result():
                existing[result["key"]] = result
                save()
    data = save()
    print(f"{len(data)} videos in {OUT}")


def build_safely(video):
    try:
        return build(video)
    except Exception as e:  # one failing video shouldn't lose the others
        print(f"{video[0]} FAILED: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    main()
