"""The final cut (video/SCRIPT.md, 15 parts): ten parts, cut on natural boundaries, the song under everything, captions burned in.

Voice: video/voice/<n>-*.m4a|wav (Anusha's and Andrii's recordings) when present, else a temporary Gemini voice per
part (Kore for Anusha, Charon for Andrii) so the cut always builds. Run from the repo root:
    .venv/bin/python video/cut3.py            # -> video/work/unseen-steps-story.mp4
Needs video/build.py's and build2.py's outputs in video/work (cards, crops) from earlier runs."""
import json
import re
import subprocess
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build  # noqa: E402

REPO, V = build.REPO, build.V
sys.path.insert(0, str(REPO / "server"))
TAKE = REPO / "clips_public/live_session7.mp4"
TURNS = json.loads((REPO / "clips_public/live_session7.json").read_text())
SONG = REPO / "clips_public/with_you_im_born_again_slow_waltz.wav"
VOICE_DIR = Path(__file__).parent / "voice"
A = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
VID = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30"]
dur = build.dur

# (part, speaker, text) from video/SCRIPT.md
PARTS = {
    1: ("Anusha", "Close your eyes."),
    2: ("Anusha", "What about now?"),
    3: ("Anusha", "You noticed the difference, right? The first clip is what a blind or partially sighted person often gets at a dance show: the music, and nothing of the dance. The second is our answer: dance you can hear."),
    4: ("Andrii", "Back in Ukraine, I did ballroom dancing for five years, and it was a big part of my childhood. So I know everything behind each dance: the steps, the timing, the grace, all the little details that make a performance what it is."),
    5: ("Anusha", "There are over two million people in the UK with sight loss. My tutor, Gerard, works with blind dancers. He told me how often, even though they hear the music, they miss what's actually happening on stage."),
    6: ("Andrii", "That's how we came up with the idea. I brought the dance experience, and Anusha brought the accessibility problem."),
    7: ("Anusha", "And my own training, commercial, contemporary and ballet growing up, and street styles now, shaped how it describes every style. So, we built Unseen Steps."),
    8: ("Andrii", "Before the performance, Gemini 4 Argon watches the rehearsal with its music, at five to eight frames a second, all in one go. It works out the structure, the key moments and what each movement means, not just where someone's arms or legs are. The studio can read and edit these show notes."),
    9: ("Anusha", "During the performance, YOLO pose tracking follows the dancer, while Gemini Live describes what's happening in under a second, even if the dancer changes something from rehearsal."),
    10: ("Andrii", "But we didn't want the AI to just guess. If the body tracking doesn't support a turn, a direction or a jump, our checker flags it, and the next line puts it right."),
    11: ("Anusha", "Dance, like code, has its own language. With Deep Research and MongoDB Atlas, we built a glossary of terms reviewed by dancers, with professional and simpler names, and every show's notes live there too."),
    13: ("Andrii", "For me, dance is five years of my childhood."),
    14: ("Anusha", "For the people Gerard works with, this could mean getting the whole performance, not just the music. And it's open source, so any studio can use it."),
    15: ("Anusha", "That's what we want Unseen Steps to do."),
}


def run(*a):
    subprocess.run([str(x) for x in a], check=True)


def voice(n):
    """The recorded part if there is one, else a temporary Gemini voice; leading/trailing silence trimmed."""
    out = V / f"vo{n}.wav"
    rec = sorted(VOICE_DIR.glob(f"{n}.*")) + sorted(VOICE_DIR.glob(f"{n}-*.*"))
    src = rec[0] if rec else None
    if not src:
        tmp = V / f"vo{n}-tts.wav"
        if not tmp.exists():
            import speech
            speech.VOICE = "Kore" if PARTS[n][0] == "Anusha" else "Charon"
            speech._synthesise(PARTS[n][1], tmp)
        src = tmp
    run("ffmpeg", "-loglevel", "error", "-y", "-i", src, "-af",
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "aresample=48000", "-ac", "2", out)
    return out


def caption_png(n, text, top=False):
    """The spoken words as a caption (burned in: the video has to work with the sound off too)."""
    png = V / f"cap{n}.png"
    build.shot(f"""<!doctype html><html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@700&display=block">
<style>html,body{{margin:0;width:1920px;height:1080px;background:transparent}}div{{position:absolute;{'left:48px;top:40px;max-width:1180px;text-align:left' if top else 'left:50%;transform:translateX(-50%);bottom:56px;max-width:1500px'};
background:rgba(20,24,38,.82);color:#f3ede2;font:700 38px/1.35 'Atkinson Hyperlegible Next',sans-serif;padding:14px 26px;border-radius:10px}}{'' if top else 'div{{text-align:center}}'}</style></head>
<body><div>{escape(text)}</div></body></html>""", png, transparent=True)
    return png


def sentences(text):
    return [s for s in re.split(r"(?<=[.?!])\s+", text) if s]


def segment(n, video_args, vf, music_args, out, vo_at=0.4, tail=0.9, length=None, music_vol=0.32, captions=True, top=False):
    """One part: picture (input 0) + its own audio or the song (input 1) + the voice, captions timed by sentence."""
    vo = voice(n) if n in PARTS else None
    total = length or ((vo_at + dur(vo) + tail) if vo else 6)
    inputs = [*video_args, *music_args]
    graph, last, k = [f"[0:v]{vf},fps=30,format=yuv420p[v0]"], "v0", 2
    if vo:
        inputs += ["-i", vo]
        vo_idx, k = 2, 3
        if captions:
            parts, t0 = sentences(PARTS[n][1]), vo_at
            span = dur(vo)
            weights = [len(s) for s in parts]
            for j, s in enumerate(parts):
                d = max(2.5, span * weights[j] / sum(weights))
                inputs += ["-i", caption_png(f"{n}_{j}", s, top)]
                graph.append(f"[{last}][{k}:v]overlay=0:0:enable='between(t,{t0:.2f},{t0 + d:.2f})'[v{k}]")
                last, t0, k = f"v{k}", t0 + d, k + 1
        graph.append(f"[1:a]volume={music_vol}[m];[{vo_idx}:a]adelay={int(vo_at * 1000)}:all=1,volume=1.15[n];"
                     f"[m][n]amix=inputs=2:normalize=0:duration=first[a0]")
    else:
        graph.append("[1:a]anull[a0]")
    graph.append(f"[{last}]fade=t=in:d=0.35,fade=t=out:st={total - 0.35:.2f}:d=0.35[v]")
    graph.append(f"[a0]afade=t=in:d=0.3,afade=t=out:st={total - 0.4:.2f}:d=0.4[a]")
    run("ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.2f}", *VID, *A, out)
    return out


def layered(html, name, starts, total):
    """A card that builds up: each element marked data-l="k" fades in (and rises slightly) at starts[k-1] seconds.
    Rendered as one background plus one transparent layer per element, composited by ffmpeg."""
    n = len(starts)
    base = html.replace("</style>", "[data-l]{visibility:hidden}</style>", 1)
    build.shot(base, V / f"{name}_0.png")
    layers = []
    for k in range(1, n + 1):
        h = html.replace("</style>", f"[data-l]{{visibility:hidden}}[data-l='{k}']{{visibility:visible}}"
                         "html,body{background:transparent!important}</style>", 1)
        build.shot(h, V / f"{name}_{k}.png", transparent=True)
        layers.append(V / f"{name}_{k}.png")
    inputs = ["-loop", "1", "-t", total, "-i", V / f"{name}_0.png"]
    chain, last = "[0:v]scale=1920:1080,fps=30,format=yuva420p[b0]", "b0"
    for k, (png, t) in enumerate(zip(layers, starts), 1):
        inputs += ["-loop", "1", "-t", total, "-i", png]
        chain += (f";[{k}:v]format=rgba,fade=t=in:st={t:.2f}:d=0.6:alpha=1[l{k}]"
                  f";[{last}][l{k}]overlay=x=0:y='if(lt(t,{t:.2f}),18,18*max(0,1-(t-{t:.2f})/0.6))'[b{k}]")
        last = f"b{k}"
    out = V / f"{name}.mp4"
    run("ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", chain + f";[{last}]format=yuv420p[v]", "-map", "[v]",
        "-t", total, "-an", *VID, out)
    return out


def song(at, length):
    return ["-ss", at, "-t", length + 1, "-i", SONG]


def panel_clip(start, length, min_at, out):
    """The take with the under-the-hood panel for each live line from min_at on."""
    sys.argv = ["cut2.py", str(TAKE), str(REPO / "clips_public/live_session7.json")]
    import cut2
    turns = [t for t in TURNS if min_at <= t["at"] < start + length]
    inputs, chain, last = ["-ss", start, "-t", length, "-i", TAKE], "[0:v]scale=1300:-2,pad=1920:1080:0:(1080-ih)/2:color=0x1e2a44,fps=30[b0]", "b0"
    for k, t in enumerate(turns):
        png = V / f"p{out.stem}_{k}.png"
        build.shot(cut2.panel(t), png, transparent=True)
        inputs += ["-i", png]
        a = max(0.0, t["at"] - start)
        b = (turns[k + 1]["at"] - start) if k + 1 < len(turns) else length
        chain += f";[{last}][{k + 1}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[b{k + 1}]"
        last = f"b{k + 1}"
    run("ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", chain, "-map", f"[{last}]", "-map", "0:a", *VID, *A, out)
    return out


ATLAS = build.HEAD + """ class="navy" style="padding:110px 140px">
<h2 data-l="1" style="font-size:80px;font-weight:800;line-height:1.05;margin:0 0 70px">Every show lives in <span style="color:#ff6cc0">MongoDB Atlas</span></h2>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:36px">
<div data-l="2" style="background:#2a3757;border-top:6px solid #ff6cc0;border-radius:14px;padding:36px"><p class="d" style="font-size:42px;font-weight:800;margin:0 0 14px">Glossary</p>
<p style="font-size:30px;line-height:1.4;margin:0;color:#d5d9e3">Terms reviewed by dancers, researched with Deep Research, with professional and simpler names.</p></div>
<div data-l="3" style="background:#2a3757;border-top:6px solid #ff6cc0;border-radius:14px;padding:36px"><p class="d" style="font-size:42px;font-weight:800;margin:0 0 14px">Hybrid Search</p>
<p style="font-size:30px;line-height:1.4;margin:0;color:#d5d9e3">Vector Search and Atlas Search together: "rotates to the right as a couple" finds natural turn.</p></div>
<div data-l="4" style="background:#2a3757;border-top:6px solid #ff6cc0;border-radius:14px;padding:36px"><p class="d" style="font-size:42px;font-weight:800;margin:0 0 14px">Show notes</p>
<p style="font-size:30px;line-height:1.4;margin:0;color:#d5d9e3">Argon's notes, the song's gaps and the rehearsal script per show; found by song name, even misspelt.</p></div>
</div></body></html>"""


def main():
    import director
    import speech
    director.client(); speech.client()
    segs = []
    blur = "crop=iw:ih*0.84:0:0,scale=1920:1080,gblur=sigma=55:steps=3,eq=brightness=-0.04"
    zoom = "scale=2400:-1,zoompan=z='min(zoom+0.0005,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=900:s=1920x1080:fps=30"
    img = REPO / "web/media/recital.jpg"
    ANDRII = REPO / "clips/andrii720.mp4"
    # 1-2: the hook, blurred: the song alone, then Gemini Live's narration
    segs.append(segment(1, ["-ss", 34, "-t", 10, "-i", TAKE], blur, song(34, 10), V / "t1.mp4", vo_at=0.5, length=10, music_vol=1.0))
    segs.append(segment(2, ["-ss", 44, "-t", 18, "-i", TAKE], blur, ["-ss", 44, "-t", 19, "-i", TAKE], V / "t2.mp4", vo_at=0.3, length=18, music_vol=1.0))
    # 3: the reveal
    v3 = voice(3)
    segs.append(segment(3, ["-ss", 44, "-t", dur(v3) + 1.5, "-i", TAKE], "scale=1920:1080", ["-ss", 44, "-t", dur(v3) + 2.5, "-i", TAKE],
                        V / "t3.mp4", music_vol=0.28, top=True))
    # 4: Andrii dancing
    segs.append(segment(4, ["-ss", 70, "-t", 40, "-i", ANDRII], "scale=1920:1080", ["-ss", 70, "-t", 41, "-i", ANDRII], V / "t4.mp4", music_vol=0.3))
    # 5-7: the why, over the studio recital print; 7 ends on the site
    segs.append(segment(5, ["-loop", "1", "-t", 30, "-i", img], zoom, song(60, 30), V / "t5.mp4"))
    segs.append(segment(6, ["-loop", "1", "-t", 30, "-i", img], zoom.replace("min(zoom+0.0005,1.12)", "min(1.06+on*0.0004,1.14)"), song(78, 30), V / "t6.mp4"))
    segs.append(segment(7, ["-loop", "1", "-t", 30, "-i", V / "crop_hero.png"], "scale=1920:1080", song(88, 30), V / "t7.mp4"))
    # 8: Argon's show notes, building up with the voice
    import build2
    v8 = voice(8)
    h = build2.notes_card()
    h = h.replace('<p class="d pk"', '<p data-l="1" class="d pk"', 1).replace('<h2 style="font-size:72px', '<h2 data-l="1" style="font-size:72px', 1)
    h = h.replace('<div><p style="font-size:28px;color:#4b5266;margin:0 0 10px">Signature', '<div data-l="2"><p style="font-size:28px;color:#4b5266;margin:0 0 10px">Signature', 1)
    h = h.replace('<div><p style="font-size:28px;color:#4b5266;margin:0 0 10px">Style', '<div data-l="3"><p style="font-size:28px;color:#4b5266;margin:0 0 10px">Style', 1)
    h = h.replace('<p style="font-size:28px;color:#4b5266;margin:0 0 12px">The song', '<p data-l="4" style="font-size:28px;color:#4b5266;margin:0 0 12px">The song', 1)
    h = h.replace('<div style="position:relative;height:110px', '<div data-l="4" style="position:relative;height:110px', 1)
    h = h.replace('<div style="position:relative;height:64px', '<div data-l="5" style="position:relative;height:64px', 1)
    L8 = dur(v8) + 1.3
    segs.append(segment(8, ["-i", layered(h, "notes", [0.3, L8 * 0.3, L8 * 0.3 + 1.2, L8 * 0.6, L8 * 0.6 + 1.0], L8 + 0.5)], "scale=1920:1080", song(100, 40), V / "t8.mp4"))
    # 9: live, under the hood (the next lines); 10: the checker catch
    v9, v10 = voice(9), voice(10)
    p9 = panel_clip(46.5, dur(v9) + 1.6, 46, V / "pan9.mp4")
    segs.append(segment(9, ["-i", p9], "scale=1920:1080", ["-i", p9], V / "t9.mp4", music_vol=0.3, top=True))
    p10 = panel_clip(38.5, dur(v10) + 1.6, 39, V / "pan10.mp4")
    segs.append(segment(10, ["-i", p10], "scale=1920:1080", ["-i", p10], V / "t10.mp4", music_vol=0.3, top=True))
    # 11: MongoDB Atlas, building up
    v11 = voice(11)
    L11 = dur(v11) + 1.3
    segs.append(segment(11, ["-i", layered(ATLAS, "atlas", [0.3, L11 * 0.3, L11 * 0.55, L11 * 0.8], L11 + 0.5)], "scale=1920:1080", song(130, 30), V / "t11.mp4"))
    # 12: a 20-dancer crew with its own narration, then the 18 styles page
    run("ffmpeg", "-loglevel", "error", "-y", "-ss", 61.5, "-t", 15.2, "-i", REPO / "data/killtest/judas-script-annotated.mp4", "-filter_complex",
        "[0:v]scale=1920:1080,fps=30,fade=t=in:d=0.35,fade=t=out:st=14.85:d=0.35[v];[0:a]afade=t=in:d=0.3,afade=t=out:st=14.8:d=0.4[a]",
        "-map", "[v]", "-map", "[a]", *VID, *A, V / "t12.mp4")
    segs.append(V / "t12.mp4")
    # 13: Andrii; 14: the recital print; 15: both, over the end card building up
    segs.append(segment(13, ["-ss", 100, "-t", 20, "-i", ANDRII], "scale=1920:1080", song(150, 20), V / "t13.mp4", tail=1.4))
    segs.append(segment(14, ["-loop", "1", "-t", 30, "-i", img], zoom, song(156, 30), V / "t14.mp4"))
    e = build.cards["c_end"]
    e = e.replace('<h1 style', '<h1 data-l="1" style', 1).replace('<p style="font-size:52px', '<p data-l="2" style="font-size:52px', 1)
    e = e.replace('<p class="d" style="font-size:46px', '<p data-l="3" class="d" style="font-size:46px', 1)
    e = e.replace('<p style="font-size:34px;color:#4b5266;margin:10px 0 0">github', '<p data-l="3" style="font-size:34px;color:#4b5266;margin:10px 0 0">github', 1)
    e = e.replace('<p style="font-size:28px;color:#5e6476', '<p data-l="4" style="font-size:28px;color:#5e6476', 1)
    e = e.replace('<div style="width:440px">', '<div data-l="1" style="width:440px">', 1)
    endv = layered(e, "endcard", [0.2, 0.9, 1.6, 2.3], 6)
    segs.append(segment(15, ["-i", endv], "scale=1920:1080", song(170, 8), V / "t15.mp4", length=6, music_vol=0.5))
    (V / "list4.txt").write_text("".join(f"file '{x}'\n" for x in segs))
    out = V / "unseen-steps-final.mp4"
    run("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", V / "list4.txt", "-c", "copy", out)
    print(out, round(dur(out), 1), "s;", ", ".join(f"{x.name} {dur(x):.1f}" for x in segs))


if __name__ == "__main__":
    main()
