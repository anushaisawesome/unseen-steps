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
from scriptwriter import (RATE, budget, keep_signature, review_script, revise, select_lines, verify_lines,  # noqa: E402
                          write_script, write_script_windowed)
from speech import speak  # noqa: E402

OUT = ROOT / "web" / "youtube-demo"
# Moments first (--keymoments): the script is built on the map's key moments, with no rewrite review and no final cut,
# so nothing a describer would keep gets reshuffled away. Output in data-keymoments.json (page: ?key).
MOMENTS_FIRST = "--keymoments" in sys.argv
WINDOWED = "--whole" not in sys.argv  # write one short stretch at a time (--whole: the old one-pass writer)

# key, YouTube id, label, style hint, clip start and end (seconds)
VIDEOS = [
    ("arcamarine", "cRil1jtScjI", "Aquamarine, Paris Cavanagh choreography", "commercial / contemporary, leaning contemporary", 0, 63),
    ("track10", "HA22LboHCww", "Track 10, Paris Cavanagh choreography", "commercial / contemporary, leaning contemporary", 0, 41),
    ("ponyboy", "8qm6Pn9kYas", "Ponyboy, Isaiah Southall choreography", "commercial", 0, 24),
    ("hiphop", "-mKzJIW9w2c", "The Royal Family: HHI NZ megacrew, 1st place 2019", "hip-hop crew choreography", 0, 180),
    ("inxi-solo", "ksRh4fxTLOs", "Streetstar 2013, Inxi: Sailor Moon vogue solo (freestyle, described from the recording)", "vogue femme", 0, 63),
    ("leiomy", "pm9emJoXvH0", "Streetstar 2013, Leiomy: vogue femme solo (freestyle, described from the recording)", "vogue femme", 0, 101),
    ("saumya", "4fzJBU7HRno", "Saumya, Red Bull Dance Your Style 2024 (freestyle, described from the recording)", "fusion: identify each style influence", 0, 180),
    ("ballet", "-yL2X-jkmCk", "Prix de Lausanne 2026, Dayeon Yeom: classical variation", "ballet", 0, 133),
    ("contemporary", "rY9PDSfEjUk", "Prix de Lausanne 2023, Ana Luisa Negrão: contemporary", "contemporary", 0, 159),
    ("waacking", "ZbLnxU-NOG0", "Eleganza Waacking Festival 2023: Team Korea", "waacking team choreography", 0, 191),
    ("tutting", "oJ6mC4DsOM4", "Sadeck: Murmuration (tutting)", "tutting", 0, 50),
    ("bharatanatyam", "TdYWOr12ONU", "IndianRaga: Vahana Alarippu", "Bharatanatyam", 0, 180),
    ("flamenco", "9JhUBiJPHMM", "Rocío Garrido: soleá", "flamenco", 0, 180),
    ("amapiano", "VV__i-NBNcU", "Amapiano Dance Championship: Gugulethu United We Stand Dancers", "amapiano", 0, 177),
    ("afrobeats", "uWqCqv6pmmU", "HomeBros: Afro dance choreography", "afrobeats", 0, 164),
    ("ballroom", "0GHkCRM8DBc", "WDSF World Open Prague: Standard final, waltz", "ballroom waltz", 0, 141),
]


def seconds(path: Path) -> float:
    with wave.open(str(path)) as f:
        return f.getnframes() / f.getframerate()


def place(lines: list[dict]) -> None:
    """No talking over each other. A key moment keeps its place: an ordinary line in its way gives way (dropping the
    later line every time lost Ponyboy's canon). Anything else that collides waits at most half a second, or is left
    out, because pushing lines later made them drift late."""
    placed = []
    for l in sorted([l for l in lines if l.get("audio")], key=lambda l: l["at"]):
        while placed and l["at"] < placed[-1]["at"] + placed[-1]["seconds"] + 0.15:
            prev = placed[-1]
            if l.get("key_moment") and not prev.get("key_moment"):
                prev["status"], prev["audio"] = "gave way to a key moment", None
                placed.pop()
                continue
            late = prev["at"] + prev["seconds"] + 0.15 - l["at"]
            if late <= 0.5:
                l["at"] = round(l["at"] + late, 2)
            else:
                l["status"], l["audio"] = "no room", None
            break
        if l.get("audio"):
            placed.append(l)


def build(video: tuple) -> dict:
    key, vid, label, style, start, end = video
    url = f"https://www.youtube.com/watch?v={vid}"
    plan = performance_map(url, style_hint=style, start=start, end=end)
    writer = write_script_windowed if WINDOWED else write_script
    script = writer(url, None, style_hint=style, plan=plan, start=start, end=end)
    if not MOMENTS_FIRST:
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

    def voice(n_line):
        n, line = n_line
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
                return
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "64k",
                            str(mp3)], check=True)
            wav.unlink()
        line["seconds"] = round(float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
            capture_output=True, text=True, check=True).stdout), 2)
        line["audio"] = line["audio_kept"] = f"audio/{mp3.name}"
        line["at"] = line["time"]

    with ThreadPoolExecutor(max_workers=6) as pool:  # every line voiced at once, not one by one
        list(pool.map(voice, enumerate(lines)))
    for line in lines:
        line.setdefault("at", line["time"])
        line.setdefault("seconds", 0.0)

    def share():
        return sum(l["seconds"] for l in lines if l.get("audio")) / (end - start)

    # The final cut: Argon, watching the video, keeps the lines a dancer would (the music stays the main thing).
    voiced = [l for l in lines if l.get("audio")]
    keep = select_lines(url, voiced, plan, end - start, start=start, end=end)  # key moments are never cut
    for n, l in enumerate(voiced):
        if n not in keep:
            l["status"] = "left for the music"
            l.pop("audio")
    # The cut must not erase the signature (it kept dropping Track 10's arm work): if a signature quality vanished,
    # its best line comes back.
    kept = [l for l in voiced if l.get("audio")]
    for back in keep_signature(voiced, kept, plan):
        if back.get("restored"):
            original = next((l for l in voiced if l["text"] == back["text"] and not l.get("audio")), None)
            if original:
                original["audio"], original["status"] = original["audio_kept"], "spoken (signature)"

    place(lines)

    spoken = [l for l in lines if l.get("audio")]
    print(f"{key}: {plan['style']['name']}, {len(spoken)}/{len(lines)} lines spoken, speech {share():.0%}")
    return {"key": key, "id": vid, "label": label, "style": plan["style"]["name"], "start": start, "end": end,
            "review": script.get("review", ""),
            "signature": [f"{x['quality']}: {x['body']}" for x in plan.get("signature", [])],
            "sections": [{"start": s["start"], "end": s["end"], "label": s["label"], "group": s.get("group", "")}
                         for s in plan["sections"]],
            "lines": [{"at": l["at"], "text": l["text"], "kind": l["kind"], "pace": l["pace"],
                       "key_moment": bool(l.get("key_moment")),
                       "priority": l.get("priority"), "audio": l.get("audio"), "status": l.get("status", "spoken"),
                       "seconds": l["seconds"]} for l in lines]}  # audio_kept stays internal


def merge():
    """Fold every finished video in parts/ into the page's data (run after each part, so the page fills in)."""
    import fcntl
    lock = open(OUT / ".merge.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)  # several videos can finish at once
    data_file = OUT / ("data-keymoments.json" if "--keymoments" in sys.argv else "data.json")
    existing = {d["key"]: d for d in json.loads(data_file.read_text())} if data_file.exists() else {}
    for part in sorted((OUT / "parts").glob("*.json")):
        d = json.loads(part.read_text())
        existing[d["key"]] = d
    order = [v[0] for v in VIDEOS]
    data = sorted(existing.values(), key=lambda d: order.index(d["key"]) if d["key"] in order else 99)
    data_file.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    (OUT / ("data-keymoments.js" if "--keymoments" in sys.argv else "data.js")).write_text(
        "window.DEMOS = " + json.dumps(data, ensure_ascii=False) + ";\n")


def main():
    wanted = {a for a in sys.argv[1:] if not a.startswith("--")}
    if "--merge" in sys.argv:
        merge()
        return
    if "--part" in sys.argv:  # one video in its own process; its result lands in parts/ and is merged straight away
        import director
        import speech
        director.client(), speech.client()
        video = next(v for v in VIDEOS if v[0] in wanted)
        if (OUT / "parts" / f"{video[0]}.json").exists():
            print(f"{video[0]}: already done, skipped")
            return
        result = build_safely(video)
        if result:
            (OUT / "parts").mkdir(exist_ok=True)
            (OUT / "parts" / f"{video[0]}.json").write_text(json.dumps(result, ensure_ascii=False))
        return
    videos = [v for v in VIDEOS if not wanted or v[0] in wanted]
    OUT.mkdir(parents=True, exist_ok=True)
    data_file = OUT / ("data-keymoments.json" if "--keymoments" in sys.argv else "data.json")
    existing = {d["key"]: d for d in json.loads(data_file.read_text())} if data_file.exists() else {}
    # Create each Gemini client once, before the threads: lazily created clients race, and the loser gets closed.
    import director
    import speech
    director.client(), speech.client()
    order = [v[0] for v in VIDEOS]

    def save():  # after every video, so the page fills in as the batch runs (refresh to see more)
        data = sorted(existing.values(), key=lambda d: order.index(d["key"]) if d["key"] in order else 99)
        data_file.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        (OUT / ("data-keymoments.js" if "--keymoments" in sys.argv else "data.js")).write_text(
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
