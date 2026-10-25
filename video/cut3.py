"""The story cut (video/SCRIPT.md): ten parts, cut on natural boundaries, the song under everything, captions burned in.

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
    2: ("Andrii", "What about now?"),
    3: ("Anusha", "You noticed the difference. The first time, you heard what a blind or partially sighted person often gets at a dance show: the music, and nothing of the dance. The second time, you heard Unseen Steps describing Andrii live, in the gaps in the music."),
    4: ("Andrii", "Back in Ukraine, I did ballroom dancing for five years, and it was a big part of my childhood. So I know what's behind every dance: the steps, the timing, the grace, all the little details that make a performance what it is."),
    5: ("Anusha", "My tutor, Gerard, works with blind dancers. He told me how often, even though they hear the music, they miss what's actually happening on stage. Andrii brought the dance, I brought the accessibility problem, and together we built Unseen Steps."),
    6: ("Andrii", "Before the show, Gemini 4 Argon watches the rehearsal with its music, all in one go. It works out the structure, the key moments and what each movement means, not just where someone's arms and legs are. Then it writes show notes the studio can read and edit, stored in MongoDB Atlas."),
    7: ("Anusha", "During the show, pose tracking follows the dancer, and Gemini Live, holding those notes, describes what's actually happening, in the gaps in the music, in under a second. Every claim is checked against the measured movement. Here it said right when he travelled left, and the next line put it right."),
    9: ("Andrii", "And it isn't just one dancer. It follows a whole crew, or one couple in a crowded competition, with everyone else blurred for privacy. And it works across eighteen styles so far, from ballet to Bharatanatyam, each in its own vocabulary."),
    10: ("Anusha", "Small studios, schools and competitions are where most people dance, and their shows never get audio description. Unseen Steps is open source, so any studio can use it, and next we're testing it with Gerard's dancers. So that everyone in the audience can experience the dance, not just the music."),
}


def run(*a):
    subprocess.run([str(x) for x in a], check=True)


def voice(n):
    """The recorded part if there is one, else a temporary Gemini voice; leading/trailing silence trimmed."""
    out = V / f"vo{n}.wav"
    rec = sorted(VOICE_DIR.glob(f"{n}-*.*"))
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
<style>html,body{{margin:0;width:1920px;height:1080px;background:transparent}}div{{position:absolute;left:50%;transform:translateX(-50%);{'top:48px' if top else 'bottom:56px'};max-width:1500px;
background:rgba(20,24,38,.82);color:#f3ede2;font:700 38px/1.35 'Atkinson Hyperlegible Next',sans-serif;padding:14px 26px;border-radius:10px;text-align:center}}</style></head>
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


def song(at, length):
    return ["-ss", at, "-t", length + 1, "-i", SONG]


def main():
    import director
    import speech
    director.client(); speech.client()
    segs = []
    # 1-2. The hook: the take blurred, the song alone, then the take with Gemini Live's narration
    blur = "crop=iw:ih*0.84:0:0,scale=1920:1080,gblur=sigma=55:steps=3,eq=brightness=-0.04"
    segs.append(segment(1, ["-ss", 34, "-t", 10, "-i", TAKE], blur, song(34, 10), V / "s1.mp4", vo_at=0.5, length=10, music_vol=1.0))
    segs.append(segment(2, ["-ss", 44, "-t", 21, "-i", TAKE], blur, ["-ss", 44, "-t", 22, "-i", TAKE], V / "s2.mp4", vo_at=0.3, length=21, music_vol=1.0))
    # 3. The reveal, sharp, under part 3
    vo3 = voice(3)
    segs.append(segment(3, ["-ss", 44, "-t", dur(vo3) + 1.5, "-i", TAKE], "scale=1920:1080", ["-ss", 44, "-t", dur(vo3) + 2.5, "-i", TAKE],
                        V / "s3.mp4", music_vol=0.28, top=True))
    # 4. Andrii dancing (his rehearsal), his own music low
    segs.append(segment(4, ["-ss", 70, "-t", 40, "-i", REPO / "clips/andrii720.mp4"], "scale=1920:1080", ["-ss", 70, "-t", 41, "-i", REPO / "clips/andrii720.mp4"],
                        V / "s4.mp4", music_vol=0.3))
    # 5. Gerard's story over the studio recital print (slow push-in)
    img = REPO / "web/media/recital.jpg"
    zoom = "scale=2400:-1,zoompan=z='min(zoom+0.0005,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=900:s=1920x1080:fps=30"
    segs.append(segment(5, ["-loop", "1", "-t", 30, "-i", img], zoom, song(60, 30), V / "s5.mp4"))
    # 6. What Argon prepared, from Atlas
    segs.append(segment(6, ["-loop", "1", "-t", 30, "-i", V / "k_notes.png"], zoom.replace("2400", "2112").replace("1.12", "1.05"), song(90, 30), V / "s6.mp4"))
    # 7. Live, under the hood: the checker catch at 39.9 s, then the next lines
    panels = V / "s7-raw.mp4"
    vo7 = voice(7)
    L = dur(vo7) + 1.6
    turns = [t for t in TURNS if 39 <= t["at"] < 38 + L]  # from the checker catch on
    sys.argv = ["cut2.py", str(TAKE), str(REPO / "clips_public/live_session7.json")]
    import cut2
    inputs, chain, last = ["-ss", 38, "-t", L, "-i", TAKE], "[0:v]scale=1300:-2,pad=1920:1080:0:(1080-ih)/2:color=0x1e2a44,fps=30[b0]", "b0"
    for k, t in enumerate(turns):
        png = V / f"p7_{k}.png"
        build.shot(cut2.panel(t), png, transparent=True)
        inputs += ["-i", png]
        a = max(0.0, t["at"] - 38)
        b = (turns[k + 1]["at"] - 38) if k + 1 < len(turns) else L
        chain += f";[{last}][{k + 1}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[b{k + 1}]"
        last = f"b{k + 1}"
    run("ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", chain, "-map", f"[{last}]", "-map", "0:a", *VID, *A, panels)
    segs.append(segment(7, ["-i", panels], "scale=1920:1080", ["-i", panels], V / "s7.mp4", music_vol=0.3, top=True))
    # 8. A 20-dancer crew, its own narration: from just before 'soloist arches' to the end of 'hair whip... tutting' (61.5-76.7 s)
    run("ffmpeg", "-loglevel", "error", "-y", "-ss", 61.5, "-t", 15.2, "-i", REPO / "data/killtest/judas-script-annotated.mp4", "-filter_complex",
        "[0:v]scale=1920:1080,fps=30,fade=t=in:d=0.35,fade=t=out:st=14.85:d=0.35[v];[0:a]afade=t=in:d=0.3,afade=t=out:st=14.8:d=0.4[a]",
        "-map", "[v]", "-map", "[a]", *VID, *A, V / "s8.mp4")
    segs.append(V / "s8.mp4")
    # 9. The crowded competition waltz (blurred for privacy), then the 18 styles page
    vo9 = voice(9)
    half = dur(vo9) * 0.5 + 0.4
    run("ffmpeg", "-loglevel", "error", "-y", "-ss", 12, "-t", half, "-i", REPO / "data/killtest/waltz-annotated.mp4", "-loop", "1", "-t", dur(vo9),
        "-i", V / "crop_styles.png", "-filter_complex", f"[0:v]scale=1920:1080,fps=30[a];[1:v]scale=1920:1080,fps=30[b];[a][b]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-an", *VID, V / "s9-pic.mp4")
    segs.append(segment(9, ["-i", V / "s9-pic.mp4"], "scale=1920:1080", song(120, 40), V / "s9.mp4"))
    # 10. The close over the site, then the end card with the song
    segs.append(segment(10, ["-loop", "1", "-t", 30, "-i", V / "crop_hero.png"], zoom.replace("1.12", "1.06"), song(150, 30), V / "s10.mp4"))
    run("ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-t", 5, "-i", V / "c_end.png", "-ss", 172, "-t", 6, "-i", SONG, "-filter_complex",
        "[0:v]scale=1920:1080,fps=30,fade=t=in:d=0.4[v];[1:a]volume=0.5,afade=t=out:st=3.5:d=1.5[a]", "-map", "[v]", "-map", "[a]", "-t", 5, *VID, *A, V / "s11.mp4")
    segs.append(V / "s11.mp4")
    (V / "list3.txt").write_text("".join(f"file '{s}'\n" for s in segs))
    out = V / "unseen-steps-story.mp4"
    run("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", V / "list3.txt", "-c", "copy", out)
    print(out, round(dur(out), 1), "s;", ", ".join(f"{s.name} {dur(s):.1f}" for s in segs))


if __name__ == "__main__":
    main()
