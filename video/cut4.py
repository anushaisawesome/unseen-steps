"""The final cut (video/SCRIPT.md, 15 parts), cut on natural boundaries, the song under everything, captions burned in.

Voice: video/voice/<n>-*.m4a|wav (Anusha's and Andrii's recordings) when present, else a temporary Gemini voice per
part (Kore for Anusha, Charon for Andrii) so the cut always builds. Run from the repo root:
    .venv/bin/python video/cut4.py            # -> video/work/unseen-steps-final.mp4
Needs video/build.py's and build2.py's outputs in video/work (cards, crops) from earlier runs."""
import json
import re
import os
import subprocess
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build  # noqa: E402

REPO, V = build.REPO, build.V
sys.path.insert(0, str(REPO / "server"))
TAKE = REPO / "clips_public/live_session7.mp4"
# the take burns in its own header and checker banner along the top (y < 84 of 720); cut that strip, keeping 16:9,
# so it never shows beside our captions
TOPCUT = "crop=1130:636:75:84"
WALTZCUT = "crop=1202:676:39:44"  # the same for the waltz render's header (y < 44 of 720)
TURNS = json.loads((REPO / "clips_public/live_session7.json").read_text())
SONG = REPO / "clips_public/with_you_im_born_again_slow_waltz.wav"
VOICE_DIR = Path(__file__).parent / "voice"
A = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
VID = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30"]
dur = build.dur
# DUB=1: an English voice track for the video already on YouTube. Every part keeps the length it has there (seconds below,
# measured from the uploaded cut), and each recorded voice is fitted into it: long pauses shortened, then sped up only if needed.
DUB = bool(os.environ.get("DUB"))
FIT = {1: 10.0, 2: 18.0, 3: 15.267, 4: 14.367, 5: 14.44, 6: 7.067, 7: 11.71, 8: 16.967, 9: 11.733, 10: 11.18, 11: 13.933,
       13: 4.1, 14: 9.767, 15: 5.2}
VO_AT = {1: 0.5, 2: 0.3}

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
    if DUB and n in FIT:
        room = FIT[n] - VO_AT.get(n, 0.4) - 0.45
        if dur(out) > room:
            tight = V / f"vo{n}-tight.wav"
            run("ffmpeg", "-loglevel", "error", "-y", "-i", out, "-af",
                "silenceremove=stop_periods=-1:stop_duration=0.3:stop_threshold=-40dB:stop_silence=0.22", tight)
            tempo = dur(tight) / room
            run("ffmpeg", "-loglevel", "error", "-y", "-i", tight, "-af", f"atempo={max(1.0, tempo):.4f}", out)
            print(f"part {n}: fitted into {room:.2f} s (pauses shortened, tempo {max(1.0, tempo):.2f}x)")
    return out


def caption_png(n, text, top=False):
    """The spoken words as a caption (burned in: the video has to work with the sound off too)."""
    png = V / f"cap{n}.png"
    build.shot(f"""<!doctype html><html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@700&display=block">
<style>html,body{{margin:0;width:1920px;height:1080px;background:transparent}}div{{position:absolute;{'left:48px;top:40px;max-width:1080px;box-sizing:border-box;text-align:left' if top else 'left:50%;transform:translateX(-50%);bottom:56px;max-width:1500px'};
background:rgba(20,24,38,.82);color:#f3ede2;font:700 38px/1.35 'Atkinson Hyperlegible Next',sans-serif;padding:14px 26px;border-radius:10px}}{'' if top else 'div{{text-align:center}}'}</style></head>
<body><div>{escape(text)}</div></body></html>""", png, transparent=True)
    return png


def label_png(name, text):
    png = V / f"label_{name}.png"
    build.shot(f"""<!doctype html><html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@700&display=block">
<style>html,body{{margin:0;width:1920px;height:1080px;background:transparent}}div{{position:absolute;right:44px;top:40px;max-width:560px;box-sizing:border-box;background:#ff48b0;
color:#1e2a44;font:700 28px/1.3 'Atkinson Hyperlegible Next',sans-serif;padding:12px 20px;border-radius:10px;box-shadow:5px 5px 0 #1e2a44}}</style></head>
<body><div>{escape(text)}</div></body></html>""", png, transparent=True)
    return png


def sentences(text):
    return [s for s in re.split(r"(?<=[.?!])\s+", text) if s]


def segment(n, video_args, vf, music_args, out, vo_at=0.4, tail=0.9, length=None, music_vol=0.32, captions=True, top=False, label=None, live_from=None):
    """One part: picture (input 0) + its own audio or the song (input 1) + the voice, captions timed by sentence."""
    vo = voice(n) if n in PARTS else None
    total = FIT[n] if DUB and n in FIT else (length or ((vo_at + dur(vo) + tail) if vo else 6))
    inputs = [*video_args, *music_args]
    graph, last, k = [f"[0:v]{vf},fps=30,setsar=1,format=yuv420p[v0]"], "v0", 2
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
    if live_from is not None:
        # the take's own captions are blurred with it: the live lines it speaks, sharp, so it works with the sound off
        for j, t in enumerate(t for t in TURNS if live_from <= t["at"] < live_from + total):
            a = t["at"] - live_from
            inputs += ["-i", caption_png(f"{n}_live{j}", t["line"], top)]
            graph.append(f"[{last}][{k}:v]overlay=0:0:enable='between(t,{a:.2f},{min(total, a + t['seconds'] + 0.4):.2f})'[v{k}]")
            last, k = f"v{k}", k + 1
    if label:
        inputs += ["-loop", "1", "-t", total, "-i", label_png(out.stem, label)]
        graph.append(f"[{k}:v]format=rgba,fade=t=in:st=0.4:d=0.5:alpha=1[lab];[{last}][lab]overlay=0:0[v{k}]")
        last, k = f"v{k}", k + 1
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
    chain, last = "[0:v]scale=1920:1080,setsar=1,fps=30,format=yuva420p[b0]", "b0"
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
    inputs, chain, last = ["-ss", start, "-t", length, "-i", TAKE], f"[0:v]{TOPCUT},scale=1300:-2,setsar=1,pad=1920:1080:0:(1080-ih)/2:color=0x1e2a44,fps=30[b0]", "b0"
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
<div data-l="2" style="background:#2a3757;border-top:6px solid #ff6cc0;border-radius:14px;padding:36px"><p class="d" style="font-size:42px;font-weight:800;margin:0 0 14px">Hybrid Search</p>
<p style="font-size:30px;line-height:1.4;margin:0;color:#d5d9e3">Movement matched to a dancer-vetted glossary: Vector Search and text search fused by rank.</p></div>
<div data-l="3" style="background:#2a3757;border-top:6px solid #ff6cc0;border-radius:14px;padding:36px"><p class="d" style="font-size:42px;font-weight:800;margin:0 0 14px">Atlas Search</p>
<p style="font-size:30px;line-height:1.4;margin:0;color:#d5d9e3">A show's song found by name, even misspelt: "andri walts" finds Andrii's waltz.</p></div>
<div data-l="4" style="background:#2a3757;border-top:6px solid #ff6cc0;border-radius:14px;padding:36px"><p class="d" style="font-size:42px;font-weight:800;margin:0 0 14px">Show notes</p>
<p style="font-size:30px;line-height:1.4;margin:0;color:#d5d9e3">Argon's notes, gaps and rehearsal script per show; the studio edits them before the night.</p></div>
</div></body></html>"""


def main():
    import director
    import speech
    director.client(); speech.client()
    segs = []
    blur = f"{TOPCUT},scale=1920:1080,setsar=1,gblur=sigma=55:steps=3,eq=brightness=-0.04"
    # still holds: ffmpeg's zoompan rounds to whole pixels each frame, so a slow push-in judders (Anusha)
    zoom = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    img = REPO / "web/media/recital.jpg"
    ANDRII = REPO / "clips/andrii720.mp4"
    # 1-2: the hook, blurred: the song alone, then Gemini Live's narration
    segs.append(segment(1, ["-ss", 34, "-t", 10, "-i", TAKE], blur, song(34, 10), V / "t1.mp4", vo_at=0.5, length=10, music_vol=1.0))
    segs.append(segment(2, ["-ss", 44, "-t", 18, "-i", TAKE], blur, ["-ss", 44, "-t", 19, "-i", TAKE], V / "t2.mp4", vo_at=0.3, length=18, music_vol=1.0, live_from=44))
    # 3: the reveal
    v3 = voice(3)
    segs.append(segment(3, ["-ss", 44, "-t", dur(v3) + 1.5, "-i", TAKE], f"{TOPCUT},scale=1920:1080", ["-ss", 44, "-t", dur(v3) + 2.5, "-i", TAKE],
                        V / "t3.mp4", music_vol=0.28, top=True))
    # 4: Andrii dancing
    segs.append(segment(4, ["-ss", 13, "-t", 40, "-i", REPO / "data/killtest/waltz-annotated.mp4"], f"{WALTZCUT},scale=1920:1080", song(40, 41), V / "t4.mp4", top=True, label="A crowded ballroom competition: the couple being described is tracked, everyone else blurred"))
    # 5-7: the why, over the studio recital print; 7 ends on the site
    gcard = V / "gerard-card.png"
    photo = (V / "gerard-photo.png").as_uri()
    build.shot(build.HEAD + f""" style="display:grid;grid-template-columns:340px 1fr;gap:70px;align-items:center;padding:0 180px">
<img src="{photo}" style="width:340px;height:340px;border-radius:50%;object-fit:cover;border:6px solid #1e2a44;box-shadow:12px 12px 0 #ff48b0">
<div><p class="d pk" style="font-size:34px;font-weight:800;margin:0 0 10px">Where the idea came from</p>
<h1 style="font-size:96px;font-weight:800;line-height:1;margin:0 0 18px">Dr Gerard Canal</h1>
<p style="font-size:40px;font-weight:700;margin:0 0 26px">Senior Lecturer in Autonomous Systems, King's College London</p>
<p style="font-size:32px;line-height:1.4;color:#4b5266;margin:0 0 30px">Anusha's robotics tutor, who dances ballroom with blind dancers.</p>
<p style="font-size:24px;color:#5e6476;margin:0">kcl.ac.uk/people/gerard-canal</p></div></body></html>""", gcard)
    v5 = voice(5)
    half5 = dur(v5) * 0.42
    run("ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-t", half5, "-i", img, "-loop", "1", "-t", dur(v5) + 1.5, "-i", gcard, "-filter_complex",
        f"[0:v]{zoom},setsar=1,fps=30[a];[1:v]scale=1920:1080,setsar=1,fps=30[b];[a][b]xfade=transition=fade:duration=0.5:offset={half5 - 0.5:.2f}[v]",
        "-map", "[v]", "-an", *VID, V / "p5.mp4")
    segs.append(segment(5, ["-i", V / "p5.mp4"], "scale=1920:1080", song(60, 30), V / "t5.mp4"))
    segs.append(segment(6, ["-ss", 2, "-t", 20, "-i", REPO / "web/media/ballet-reveal.mp4"], "scale=1920:1080", ["-ss", 2, "-t", 21, "-i", REPO / "web/media/ballet.mp4"], V / "t6.mp4", music_vol=0.3, top=True, label="A ballet solo described and checked against the tracked pose"))
    segs.append(segment(7, ["-ss", 8, "-t", 14, "-stream_loop", "1", "-i", REPO / "web/media/ballet.mp4"], "scale=1920:1080", ["-ss", 8, "-t", 15, "-stream_loop", "1", "-i", REPO / "web/media/ballet.mp4"], V / "t7.mp4", music_vol=0.3, label="The same narration works for any style"))
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
    jl = label_png("t12", "Not just one dancer: a 20-dancer crew, every dancer tracked, its canon described (1MILLION, IDL Seoul)")
    run("ffmpeg", "-loglevel", "error", "-y", "-ss", 61.5, "-t", 15.6, "-i", REPO / "data/killtest/judas-script-annotated.mp4", "-loop", "1", "-t", 15.6, "-i", jl,
        "-filter_complex",
        "[0:v]scale=1920:1080,setsar=1,fps=30[b];[1:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1[l];[b][l]overlay=0:0,fade=t=in:d=0.35,fade=t=out:st=14.2:d=1.4[v];"
        "[0:a]afade=t=in:d=0.3,afade=t=out:st=14.2:d=1.4[a]",
        "-map", "[v]", "-map", "[a]", "-t", 15.6, *VID, *A, V / "t12.mp4")
    segs.append(V / "t12.mp4")
    # 13: Andrii; 14: the recital print; 15: both, over the end card building up
    segs.append(segment(13, ["-ss", 75, "-t", 16, "-i", REPO / "data/killtest/waltz-annotated.mp4"], f"{WALTZCUT},scale=1920:1080", song(150, 21), V / "t13.mp4", tail=1.4, top=True, label="Ballroom, the style Andrii grew up dancing"))
    phone = "scale=-2:840,pad=1920:1080:(ow-iw)/2:28:color=0xf3ede2"
    segs.append(segment(14, ["-ss", 10.5, "-t", 30, "-i", V / "venue-test.mp4"], phone, song(156, 30), V / "t14.mp4", label="The venue page with a screen reader: every control labelled, each line read aloud"))
    e = build.cards["c_end"]
    e = e.replace('<h1 style', '<h1 data-l="1" style', 1).replace('<p style="font-size:52px', '<p data-l="2" style="font-size:52px', 1)
    e = e.replace('<p class="d" style="font-size:46px', '<p data-l="3" class="d" style="font-size:46px', 1)
    e = e.replace('<p style="font-size:34px;color:#4b5266;margin:10px 0 0">github', '<p data-l="3" style="font-size:34px;color:#4b5266;margin:10px 0 0">github', 1)
    e = e.replace('<p style="font-size:28px;color:#5e6476', '<p data-l="4" style="font-size:28px;color:#5e6476', 1)
    e = e.replace('<div style="width:440px">', '<div data-l="1" style="width:440px">', 1)
    endv = layered(e, "endcard", [0.2, 0.9, 1.6, 2.3], 6)
    segs.append(segment(15, ["-i", endv], "scale=1920:1080", song(170, 8), V / "t15.mp4", length=5.2, music_vol=0.5))
    (V / "list4.txt").write_text("".join(f"file '{x}'\n" for x in segs))
    out = V / ("unseen-steps-dub.mp4" if DUB else "unseen-steps-final.mp4")
    run("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", V / "list4.txt", "-c", "copy", out)
    print(out, round(dur(out), 1), "s;", ", ".join(f"{x.name} {dur(x):.1f}" for x in segs))


if __name__ == "__main__":
    main()
