# The demo video

The submitted video (2:59, 1080p) is on YouTube: https://youtu.be/4aadm47Nk1g. The file, `unseen-steps-demo.mp4`, is in
the **private** clips repo under `submission/` (https://github.com/anushaisawesome/unseen-steps-clips). It isn't in this
public repo because it includes other crews' choreography (1MILLION at IDL Seoul; the competition waltz).

It follows the 15-part script in `SCRIPT.md`; `cut4.py` builds it.

## Structure (2:59)

| Time | Part | Picture | Sound |
| --- | --- | --- | --- |
| 0:00 | 1 "Close your eyes." | Andrii's live take 34-44 s, blurred | The song only |
| 0:10 | 2 "What about now?" | Same blur, 44-62 s, with sharp captions of Gemini Live's lines | The take's own audio: the song and the live narration |
| 0:28 | 3 The difference | The blur clears: the take from 44 s with skeleton and captions | Voice over the take |
| 0:43 | 4 Andrii, ballroom in Ukraine | Competition waltz 13-27 s, the described couple tracked, everyone else blurred | Song |
| 0:58 | 5 Two million people, Gerard | The studio recital illustration, then Gerard Canal's KCL card | Song |
| 1:12 | 6 How the idea came about | Ballet solo with tracked pose (`web/media/ballet-reveal.mp4`) | Its own music |
| 1:19 | 7 Anusha's training | Ballet solo, narrated | Its own music |
| 1:31 | 8 Argon's show notes | Notes card from Andrii's rehearsal, building up | Song |
| 1:48 | 9 Live, under the hood | Take 46.5 s on, with the panel per line (gap, rehearsal note, latency, checker) | Take |
| 2:00 | 10 The checker | Take 38.5 s on: the checker flags "rightwards" (measured travel was left) | Take |
| 2:11 | 11 MongoDB Atlas | Hybrid Search, Atlas Search and show notes card, building up | Song |
| 2:25 | 12 A 20-dancer crew | 1MILLION, IDL Seoul (`data/killtest/judas-script-annotated.mp4` 61.5 s on), every dancer tracked | Its own narration |
| 2:40 | 13 "For me, dance is five years of my childhood." | Competition waltz 75 s on | Song |
| 2:44 | 14 Gerard's dancers, open source | The venue page on a phone with the screen-reader test (10.5 s on) | Song |
| 2:54 | 15 "That's what we want Unseen Steps to do." | End card | Song |

The song is `with_you_im_born_again_slow_waltz.wav`, the music Andrii dances to in the live takes (kept in the private
clips repo under `music/`); in the take, song time equals take time. Labels (pink, top right) say why each clip is
there; spoken words are burned in as captions so the video works with the sound off.

## Rebuild

Needs ffmpeg, Chrome (set `CHROME=` to its path if it isn't found), the repo's `.venv`, the clips in `clips_public/`
and `data/killtest/` (from the clips repo), and the cards `build.py` and `build2.py` leave in `video/work/`.

```sh
.venv/bin/python video/cut4.py      # -> video/work/unseen-steps-final.mp4
```

Voices come from `video/voice/<part>.m4a` (or `<part>-*.m4a`) when present, otherwise a Gemini TTS stand-in (Kore for
Anusha, Charon for Andrii). Keep it under 3:00 (DeepMind's limit). `cut2.py` and `cut3.py` are earlier cuts.
