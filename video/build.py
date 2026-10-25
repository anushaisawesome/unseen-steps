"""Cut the 3-minute demo video: title cards in the site's studio-print style, Andrii's live take (session 7),
crops of the live site, a Gemini-voiced voice-over (swap in Anusha's recording later), and real narration clips."""
import json
import subprocess
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V = Path(__file__).resolve().parent / "work"  # generated cards, voice-over and segments (gitignored)
V.mkdir(exist_ok=True)
import os
CHROME = os.environ.get("CHROME") or next((c for c in (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe") if Path(c).exists()), "google-chrome")
TAKE = REPO / "clips_public/live_session7.mp4"
sys.path.insert(0, str(REPO / "server"))


def run(*a):
    subprocess.run([str(x) for x in a], check=True)


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True, check=True).stdout)


def shot(html, png, transparent=False, h=1080):
    src = V / (png.stem + ".html")
    src.write_text(html)
    extra = ["--default-background-color=00000000"] if transparent else []
    for _ in range(3):  # Chrome's exit code is unreliable; the file is what counts
        png.unlink(missing_ok=True)
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size=1920,{h}",
                        "--virtual-time-budget=4000", *extra, f"--screenshot={png}", src.as_uri()], capture_output=True)
        if png.exists() and png.stat().st_size > 1000:
            return
    raise RuntimeError(f"couldn't render {png.name}")


HEAD = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet"
href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;700&family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&display=block">
<style>html,body{margin:0;width:1920px;height:1080px;overflow:hidden}
body{font-family:'Atkinson Hyperlegible Next',sans-serif;background:#f3ede2;color:#1e2a44;box-sizing:border-box;padding:120px 140px}
h1,h2,.d{font-family:'Bricolage Grotesque',sans-serif;letter-spacing:-0.03em;margin:0}
.pk{color:#b5106f}.navy{background:#1e2a44;color:#f3ede2}
.hl{background:linear-gradient(transparent 62%,rgba(255,72,176,.55) 62%,rgba(255,72,176,.55) 92%,transparent 92%)}
</style></head><body"""

MARK = (REPO / "web/media/mark.svg").read_text().replace('fill="currentColor"', 'fill="#1e2a44"')

cards = {
    "c_hook": HEAD + """ class="navy" style="display:grid;place-items:center;text-align:center">
<div><h1 style="font-size:190px;font-weight:800;line-height:1">Close your eyes.</h1>
<p style="font-size:44px;color:#aeb4c4;margin-top:40px">This is Andrii, dancing a waltz, described live.</p></div></body></html>""",
    "c_problem": HEAD + """ style="display:grid;grid-template-columns:700px 1fr;gap:100px;align-items:center">
<div><p class="d pk" style="font-size:260px;font-weight:800;line-height:1;margin:0">2M+</p>
<p style="font-size:40px;color:#4b5266;margin:10px 0 0">people in the UK live with sight loss (RNIB)</p></div>
<div><h2 style="font-size:84px;font-weight:800;line-height:1.05">At a studio show, they hear the music. <span class="hl">The dancing is silent.</span></h2>
<p style="font-size:38px;line-height:1.4;color:#4b5266;margin-top:40px">Professional audio description of dance is rare and goes to big venues. Recitals, school shows and competitions never get it.</p></div></body></html>""",
    "c_how": HEAD + """><h2 style="font-size:84px;font-weight:800;line-height:1.05;margin-bottom:70px">Prepared from rehearsal, <span class="pk">delivered live</span></h2>
<div style="display:grid;gap:44px">""" + "".join(
        f"""<div style="display:flex;gap:26px;align-items:center"><p class="d" style="width:270px;font-size:40px;font-weight:800;margin:0;color:{c}">{row}</p>"""
        + "".join(f"""<div style="flex:1;background:#fbf8f2;border:3px solid #1e2a44;border-radius:16px;padding:30px 32px;box-shadow:8px 8px 0 #ff48b0">
<p class="d" style="font-size:40px;font-weight:800;margin:0">{t}</p><p style="font-size:29px;color:#4b5266;margin:8px 0 0">{s}</p></div>""" + ("<p style='font-size:60px;margin:0;color:#ff48b0'>&#8594;</p>" if k < 2 else "")
                  for k, (t, s) in enumerate(items)) + "</div>"
        for row, c, items in [
            ("Before the show", "#1e2a44", [("Rehearsal video", "uploaded by the studio"), ("Gemini 4 Argon", "show notes, key moments, the gaps"), ("MongoDB Atlas", "every line checked, stored per show")]),
            ("During the show", "#b5106f", [("Camera and pose", "YOLO tracks the dancer"), ("Gemini Live", "narrates what happens, in the gaps"), ("Earphones", "each claim checked against the pose")])]) + "</div></body></html>",
    "c_end": HEAD + """ style="display:grid;grid-template-columns:1fr 520px;gap:80px;align-items:center">
<div><h1 style="font-size:150px;font-weight:800;line-height:.95">Unseen Steps</h1>
<p style="font-size:52px;margin:34px 0 60px;color:#4b5266">Experience <span class="hl" style="color:#1e2a44;font-weight:700">the dance</span>, not just the music.</p>
<p class="d" style="font-size:46px;font-weight:800;margin:0">unseen-steps-studio.vercel.app</p>
<p style="font-size:34px;color:#4b5266;margin:10px 0 0">github.com/anushaisawesome/unseen-steps</p>
<p style="font-size:28px;color:#5e6476;margin:50px 0 0">Anusha, Andrii and Nastia · Encode London 2026 · Gemini 4 Argon, Gemini Live, MongoDB Atlas</p></div>
<div style="width:440px">""" + MARK.replace("<svg ", '<svg style="width:440px;height:auto" ') + "</div></body></html>",
}
lower = {
    "l_live": "Live: Gemini Live narrating Andrii from the camera, in the gaps in the music",
    "l_check": "Every claim is checked against his measured pose",
}

VO = {
    "v_hook": "Close your eyes for a moment. This is Andrii, dancing a waltz, described live by Unseen Steps.",
    "v_problem": "More than two million people in the UK live with sight loss. At a dance show they hear the music, but the dancing itself is silent. Professional audio description of dance is rare, and goes to big venues, so the shows put on by small studios, schools and competitions never get it.",
    "v_how": "Unseen Steps gives those studios description of their own shows. Before the show, the studio uploads a rehearsal video. Gemini 4 Argon watches and listens like an expert describer, and writes show notes: the style, the key moments, and the gaps in the music where a line fits. Every line is checked against the video, and the notes are stored in MongoDB Atlas. On the night, pose tracking follows the dancer, and Gemini Live, holding those notes, describes what the dancer actually does, in the gaps, in about a second.",
    "v_styles": "Because the notes are written for each piece, it works for whatever a studio teaches. Seventeen choreographed pieces, from a Prix de Lausanne variation to a kids' tap recital, each in its own vocabulary, with the music left as the main thing.",
    "v_end": "Next: an editor for studios, testing with blind audiences at real recitals, and a training tool for blind dancers. Unseen Steps. Experience the dance, not just the music.",
}


def main():
    import director
    import speech
    director.client(); speech.client()
    for name, html in cards.items():
        if not (V / f"{name}.png").exists():
            shot(html, V / f"{name}.png")
    for name, text in lower.items():
        if not (V / f"{name}.png").exists():
            shot(f"""<!doctype html><html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@700&display=block">
<style>html,body{{margin:0;width:1920px;height:1080px;background:transparent}}div{{position:absolute;left:80px;top:60px;background:#1e2a44;color:#f3ede2;
font:700 36px 'Atkinson Hyperlegible Next',sans-serif;padding:18px 28px;border-radius:10px;box-shadow:6px 6px 0 #ff48b0}}</style></head>
<body><div>{text}</div></body></html>""", V / f"{name}.png", transparent=True)
    # site crops
    if not (V / "site-full.png").exists():
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1920,5200", "--virtual-time-budget=6000",
                        f"--screenshot={V / 'site-full.png'}", "https://unseen-steps-studio.vercel.app/"], check=True, capture_output=True)
    for name, text in VO.items():
        if not (V / f"{name}.wav").exists():
            speech.speak(text, V / f"{name}.wav")
        print(name, round(dur(V / f"{name}.wav"), 1), "s")


if __name__ == "__main__":
    main()
