"""Final cut. Usage: cut2.py TAKE.mp4 TURNS.json [SONG] [--hook START]

TURNS.json is live.py's --record log: [{line, at, seconds, latency, checker}, ...] (song times = take times).
SONG, if given, is the music file live.py played; the first 10 s of the video are that music alone.
--hook START: the take time where the hook begins (music only for 10 s, then 20 s with narration)."""
import ast
import json
import subprocess
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build  # noqa: E402

REPO, V = build.REPO, build.V
sys.path.insert(0, str(REPO / "server"))
A = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
VID = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30"]
dur = build.dur


def run(*a):
    subprocess.run([str(x) for x in a], check=True)


argv = sys.argv[1:]
if "--hook" in argv:
    i = argv.index("--hook"); HOOK_ARG = argv[i + 1]; del argv[i:i + 2]
args = argv
TAKE, TURNS = Path(args[0]), json.loads(Path(args[1]).read_text())
SONG = Path(args[2]) if len(args) > 2 else None
HOOK = float(HOOK_ARG) if "HOOK_ARG" in globals() else 15.0
REVEAL = 20.0  # seconds of the take shown with the under-the-hood panel

from db import db  # noqa: E402
show = db()["shows"].find_one({"name": "Demo: Andrii, waltz"})
gaps = show["gaps"] if isinstance(show["gaps"], list) else json.loads(show["gaps"])
script = show.get("script") or []
if isinstance(script, str):
    script = ast.literal_eval(script)


def panel(turn):
    """One under-the-hood card for a spoken line: what Gemini Live was given and what came back."""
    at = turn["at"]
    gap = next(((a, b) for a, b in gaps if a - 0.6 <= at <= b), None)
    near = min(script, key=lambda l: abs(l["time"] - at)) if script else None
    ok = turn.get("checker", "ok") == "ok"
    rows = [("Gap in the song", f"{gap[0]:.1f} to {gap[1]:.1f} s" if gap else f"{at:.1f} s")]
    if near:
        rows.append(("Rehearsal notes here", f"&ldquo;{escape(near['text'])}&rdquo;"))
    rows.append(("Gemini Live said" + (f", {turn['latency']:.1f} s after the prompt" if turn.get("latency") is not None else ""),
                 f"<b>&ldquo;{escape(turn['line'])}&rdquo;</b>"))
    if "checker" in turn:
        rows.append(("Pose checker", "consistent with the measured movement" if ok else
                     f"<span style='color:#ff6cc0'>flagged: {escape(turn['checker'])}.</span> Gemini is told, and the next line puts it right."))
    body = "".join(f'<p style="font-size:22px;color:#9aa3b8;margin:0 0 6px">{k}</p><p style="font-size:30px;line-height:1.3;margin:0 0 26px">{v}</p>'
                   for k, v in rows)
    return f"""<!doctype html><html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;700&family=Bricolage+Grotesque:opsz,wght@12..96,800&display=block">
<style>html,body{{margin:0;width:1920px;height:1080px;background:transparent;font-family:'Atkinson Hyperlegible Next',sans-serif}}
.p{{position:absolute;right:0;top:0;width:620px;height:1080px;box-sizing:border-box;padding:56px 44px;background:#1e2a44;color:#f3ede2}}
h3{{font-family:'Bricolage Grotesque',sans-serif;font-size:34px;margin:0 0 34px;color:#ff6cc0}}</style></head>
<body><div class="p"><h3>Under the hood, live</h3>{body}</div></body></html>"""


def main():
    # 1. hook: 10 s of music alone (the song, or the take before narration), then 20 s with the narration, on black
    hook_audio = V / "hook.wav"
    if SONG:
        run("ffmpeg", "-loglevel", "error", "-y", "-ss", HOOK, "-t", 10, "-i", SONG, "-ss", HOOK + 10, "-t", 20, "-i", TAKE,
            "-filter_complex", "[0:a]aresample=48000,afade=t=in:d=1[a0];[1:a]aresample=48000[a1];[a0][a1]concat=n=2:v=0:a=1[a]",
            "-map", "[a]", "-ac", "2", hook_audio)
    else:
        run("ffmpeg", "-loglevel", "error", "-y", "-ss", HOOK, "-t", 30, "-i", TAKE, "-vn", "-ac", "2", "-ar", "48000", hook_audio)
    # The picture for the hook: the same 30 s of the take, blurred until no step can be made out (light, colour and
    # movement only), with one line of context over the first 10 s. The burned-in caption band is cropped off first.
    build.shot("""<!doctype html><html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@700&family=Bricolage+Grotesque:opsz,wght@12..96,800&display=block">
<style>html,body{margin:0;width:1920px;height:1080px;background:transparent}div{position:absolute;left:0;right:0;bottom:120px;text-align:center;color:#f3ede2;
font:700 46px 'Atkinson Hyperlegible Next',sans-serif;text-shadow:0 2px 18px rgba(0,0,0,.6);padding:0 200px;line-height:1.35}</style></head>
<body><div>Most people with sight loss see some light and movement.<br>At a dance show, this is often all they get.</div></body></html>""", V / "hooktext.png", transparent=True)
    run("ffmpeg", "-loglevel", "error", "-y", "-ss", HOOK, "-t", 30, "-i", TAKE, "-loop", "1", "-t", 30, "-i", V / "hooktext.png", "-i", hook_audio,
        "-filter_complex", "[0:v]crop=iw:ih*0.84:0:0,scale=1920:1080,fps=30,gblur=sigma=55:steps=3,eq=brightness=-0.04:saturation=1.1[b];"
        "[1]format=rgba,fade=t=in:st=0.6:d=0.8:alpha=1,fade=t=out:st=8.8:d=0.8:alpha=1[t];[b][t]overlay=0:0[v]",
        "-map", "[v]", "-map", "2:a", "-t", 30, *VID, *A, V / "t01.mp4")

    # 2. the reveal: the same moment, now seen, with the under-the-hood panel for each line
    start = HOOK + 10
    turns = [t for t in TURNS if start - 5 <= t["at"] < start + REVEAL]  # a flag shown just before the reveal stays on screen
    inputs, chain, last = ["-ss", start, "-t", REVEAL, "-i", TAKE], "[0:v]scale=1300:-2,pad=1920:1080:0:(1080-ih)/2:color=0x1e2a44,fps=30[b0]", "b0"
    for k, t in enumerate(turns):
        png = V / f"panel{k}.png"
        build.shot(panel(t), png, transparent=True)
        inputs += ["-i", png]
        a = max(0.0, t["at"] - start)
        b = (turns[k + 1]["at"] - start) if k + 1 < len(turns) else REVEAL
        chain += f";[{last}][{k + 1}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[b{k + 1}]"
        last = f"b{k + 1}"
    run("ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", chain, "-map", f"[{last}]", "-map", "0:a", *VID, *A, V / "t02.mp4")

    # 3. the explanation
    def card(png, audio, out, zoom=False, pad=0.8):
        total = dur(audio) + pad + 0.3
        vf = (f"scale=2112:-1,zoompan=z='min(zoom+0.00025,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(total * 30) + 5}:s=1920x1080:fps=30"
              if zoom else "scale=1920:1080,fps=30")
        run("ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", png, "-i", audio, "-filter_complex",
            f"[0]{vf}[v];[1]adelay=300:all=1,apad[a]", "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}", *VID, *A, out)
        return out

    def footage(clip, start, voice, label, out):
        total = dur(voice) + 0.8
        run("ffmpeg", "-loglevel", "error", "-y", "-ss", start, "-t", total, "-i", clip, "-i", V / label, "-i", voice, "-filter_complex",
            "[0:v]scale=1920:1080,fps=30[b];[b][1]overlay=0:0[v];[0:a]volume=0.25[m];[2:a]adelay=300:all=1[n];[m][n]amix=inputs=2:normalize=0:duration=first[a]",
            "-map", "[v]", "-map", "[a]", *VID, *A, out)
        return out

    segs = [V / "t01.mp4", V / "t02.mp4",
            card(V / "k_why.png", V / "w_why.wav", V / "t03.mp4"),
            card(V / "k_notes.png", V / "w_notes.wav", V / "t04.mp4", zoom=True),
            card(V / "c_how.png", V / "w_live.wav", V / "t05.mp4"),
            footage(REPO / "data/killtest/waltz-annotated.mp4", 12, V / "w_world.wav", "m_world.png", V / "t06.mp4"),
            card(V / "crop_wave.png", V / "w_styles.wav", V / "t07.mp4"),
            group_clip(V / "t08.mp4"),
            card(V / "k_next.png", V / "w_next.wav", V / "t09.mp4"),
            card(V / "c_end.png", V / "w_end.wav", V / "t10.mp4", pad=2.5)]
    (V / "list2.txt").write_text("".join(f"file '{s}'\n" for s in segs))
    out = V / "unseen-steps-demo-v2.mp4"
    run("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", V / "list2.txt", "-c", "copy", out)
    print(out, round(dur(out), 1), "s;", ", ".join(f"{s.name} {dur(s):.1f}" for s in segs))


def group_clip(out):
    """A 20-dancer crew piece with every dancer tracked, and its own narration (canon, tutting), 11 s."""
    run("ffmpeg", "-loglevel", "error", "-y", "-ss", 66, "-t", 11, "-i", REPO / "data/killtest/judas-script-annotated.mp4", "-i", V / "m_group.png",
        "-filter_complex", "[0:v]scale=1920:1080,fps=30[b];[b][1]overlay=0:0[v];[0:a]afade=t=in:d=0.3,afade=t=out:st=10.4:d=0.6[a]",
        "-map", "[v]", "-map", "[a]", *VID, *A, out)
    return out


def build_board():
    """The listener board with the Esmeralda line playing (the real narration clip)."""
    d = json.load(open(REPO / "web/youtube-demo/data.json"))
    vids = {v["key"]: v for v in (d if isinstance(d, list) else d["videos"])}
    line = next(l for l in vids["ballet"]["lines"] if l.get("audio") and l["text"].startswith("Hand on hip"))
    clip = REPO / "web/youtube-demo" / line["audio"]
    total = dur(clip) + 1.6
    out = V / "t08.mp4"
    run("ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", V / "crop_board.png", "-i", clip, "-filter_complex",
        "[0]scale=1920:1080,fps=30[v];[1]adelay=600:all=1,apad[a]", "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}", *VID, *A, out)
    return out


if __name__ == "__main__":
    main()
