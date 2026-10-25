"""Second cut: new cards (why, what Argon prepared, reads the world, next) and the revised voice-over."""
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build  # noqa: E402  (HEAD, shot, MARK, dur)

REPO = build.REPO
V = build.V
sys.path.insert(0, str(REPO / "server"))
HEAD, shot = build.HEAD, build.shot

VO = {
    "w_why": "Dance is a visual art form, so for the two million people in the UK with sight loss, a dance show is mostly music. Audio description exists, but it's expensive and goes to big venues. The shows put on by small studios, schools and competitions, where most dancers actually perform, never get it.",
    "w_notes": "Unseen Steps lets a studio describe its own show. Before the show, it uploads a rehearsal video. Gemini 4 Argon holds the whole performance in one context. It maps the sections, the style, the key moments and the gaps in the song, then re-watches each section closely and writes show notes the way an expert describer would. Every line is checked against the video, and the notes are stored per show in MongoDB Atlas, with a glossary vetted by dancers.",
    "w_live": "On the night, pose tracking follows the dancer, and Gemini Live holds those notes. In each gap it describes what the dancer actually does, in about a second, and a checker compares every claim with the measured pose.",
    "w_world": "Real venues are messy. In a crowded competition it follows the right couple and blurs everyone else. A step it can't confirm is described rather than named, and if it loses the dancer, it goes quiet rather than guess.",
    "w_styles": "Because the notes are written for each piece, it works for whatever a studio teaches: eighteen choreographed pieces so far, from a Prix de Lausanne variation to a kids' tap recital, each in its own vocabulary.",
    "w_next": "People stay in charge: the studio reads and edits the notes before the show. This started with my robotics tutor, who dances ballroom with blind dancers. We're open-sourcing Unseen Steps so any studio can run it, and next we're testing it with blind audiences at real recitals, so more people can enjoy dance.",
}


def notes_card():
    from db import db
    s = db()["shows"].find_one({"name": "Demo: Andrii, waltz"})
    plan = s["plan"] if isinstance(s["plan"], dict) else ast.literal_eval(s["plan"])
    gaps = s["gaps"] if isinstance(s["gaps"], list) else json.loads(s["gaps"])
    length = plan["sections"][-1]["end"]
    pct = lambda t: f"{100 * t / length:.2f}%"
    bands = "".join(f'<div style="position:absolute;left:{pct(x["start"])};width:{100 * (x["end"] - x["start"]) / length:.2f}%;top:0;bottom:0;'
                    f'border-left:2px solid #1e2a44;padding:10px 12px;font-size:24px;line-height:1.2">{x["label"]}</div>' for x in plan["sections"])
    ticks = "".join(f'<i style="position:absolute;left:{pct(a)};width:{100 * (b - a) / length:.2f}%;top:12px;bottom:12px;background:#ff48b0;border-radius:4px"></i>'
                    for a, b in gaps)
    sig = [line.strip("- ").split(":")[0] for line in s["show_notes"].splitlines() if line.startswith("- ")][:2]
    return HEAD + f""" style="padding:100px 140px">
<p class="d pk" style="font-size:34px;font-weight:800;margin:0">What Gemini 4 Argon prepared from Andrii's rehearsal</p>
<h2 style="font-size:72px;font-weight:800;line-height:1.05;margin:14px 0 46px">Show notes, stored in MongoDB Atlas</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:60px;margin-bottom:54px">
<div><p style="font-size:28px;color:#4b5266;margin:0 0 10px">Signature of this piece</p>
{''.join(f'<p style="font-size:34px;font-weight:700;margin:0 0 12px">{x}</p>' for x in sig)}</div>
<div><p style="font-size:28px;color:#4b5266;margin:0 0 10px">Style, with the evidence it saw</p>
<p style="font-size:34px;font-weight:700;margin:0">{plan['style']['name'].capitalize()}: {', '.join(plan['style']['evidence'][:2])}</p></div></div>
<p style="font-size:28px;color:#4b5266;margin:0 0 12px">The song: {len(plan['sections'])} sections, and {len(gaps)} gaps where a line fits</p>
<div style="position:relative;height:110px;border-top:4px solid #1e2a44;margin-bottom:14px">{bands}</div>
<div style="position:relative;height:64px;background:#fbf8f2;border:3px solid #1e2a44;border-radius:12px">{ticks}</div>
</body></html>"""


cards = {
    "k_why": HEAD + """ style="display:grid;grid-template-columns:700px 1fr;gap:100px;align-items:center">
<div><p class="d pk" style="font-size:260px;font-weight:800;line-height:1;margin:0">2M+</p>
<p style="font-size:40px;color:#4b5266;margin:10px 0 0">people in the UK live with sight loss (RNIB)</p></div>
<div><h2 style="font-size:84px;font-weight:800;line-height:1.05">Dance is a visual art. <span class="hl">For them, a show is mostly music.</span></h2>
<p style="font-size:38px;line-height:1.4;color:#4b5266;margin-top:40px">Audio description is expensive and goes to big venues. Small studios, schools and competitions, where most dancers perform, never get it.</p></div></body></html>""",
    "k_next": HEAD + """><h2 style="font-size:96px;font-weight:800;line-height:1.02;margin:0 0 60px">Open source, <span class="pk">for every studio</span></h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:56px 80px">
<div><p class="d" style="font-size:42px;font-weight:800;margin:0">People stay in charge</p><p style="font-size:32px;color:#4b5266;margin:10px 0 0">The studio reads and edits its show notes before the night.</p></div>
<div><p class="d" style="font-size:42px;font-weight:800;margin:0">Where it started</p><p style="font-size:32px;color:#4b5266;margin:10px 0 0">Gerard Canal (KCL robotics), who dances ballroom with blind dancers.</p></div>
<div><p class="d" style="font-size:42px;font-weight:800;margin:0">Next</p><p style="font-size:32px;color:#4b5266;margin:10px 0 0">Testing with blind audiences at real recitals, then whole groups live.</p></div>
<div><p class="d" style="font-size:42px;font-weight:800;margin:0">Open source</p><p style="font-size:32px;color:#4b5266;margin:10px 0 0">github.com/anushaisawesome/unseen-steps</p></div>
</div></body></html>""",
}
lower = {
    "m_world": "Crowded, handheld competition footage: the couple being described is tracked; everyone else is blurred for privacy",
    "m_styles": "18 choreographed pieces, each in its own vocabulary: unseen-steps-studio.vercel.app",
    "m_group": "A 20-dancer crew (1MILLION, IDL Seoul): every dancer tracked; canons, formations and tutting described",
}


def main():
    import director
    import speech
    director.client(); speech.client()
    cards["k_notes"] = notes_card()
    for name, html in cards.items():
        shot(html, V / f"{name}.png")
    for name, text in lower.items():
        build.shot(f"""<!doctype html><html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@700&display=block">
<style>html,body{{margin:0;width:1920px;height:1080px;background:transparent}}div{{position:absolute;left:80px;top:60px;max-width:1500px;background:#1e2a44;color:#f3ede2;
font:700 36px 'Atkinson Hyperlegible Next',sans-serif;padding:18px 28px;border-radius:10px;box-shadow:6px 6px 0 #ff48b0}}</style></head>
<body><div>{text}</div></body></html>""", V / f"{name}.png", transparent=True)
    # crops of the live site (light mode) for the "where the words go" shot
    light = V / "site-light.png"
    if not light.exists():
        import subprocess
        subprocess.run([build.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1280,4200",
                        "--virtual-time-budget=6000", "--blink-settings=preferredColorScheme=1", f"--screenshot={light}",
                        "https://unseen-steps-studio.vercel.app/"], capture_output=True)
    for name, y in (("crop_hero", 0), ("crop_wave", 850), ("crop_board", 1830)):
        import subprocess
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(light), "-vf", f"crop=1280:720:0:{y},scale=1920:1080", str(V / f"{name}.png")], check=True)
    for name, text in VO.items():
        if not (V / f"{name}.wav").exists():  # sentence by sentence: long takes fail the caption check
            import re, subprocess
            parts = []
            for k, sentence in enumerate(re.split(r"(?<=[.:])\s+", text)):
                parts.append(speech.speak(sentence, V / f"{name}-{k}.wav"))
            listing = V / f"{name}.txt"
            listing.write_text("".join(f"file '{q}'\nfile '{V / 'gap.wav'}'\n" for q in parts))
            if not (V / "gap.wav").exists():
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.28", str(V / "gap.wav")], check=True)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-ar", "24000", "-ac", "1", str(V / f"{name}.wav")], check=True)
        print(name, round(build.dur(V / f"{name}.wav"), 1), "s")


if __name__ == "__main__":
    main()
