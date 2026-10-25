# The demo video

`unseen-steps-demo-final.mp4` (2:58, 1080p) is in the **private** clips repo release `video-1`
(https://github.com/anushaisawesome/unseen-steps-clips/releases/tag/video-1), with the `work/` folder of every
generated card, voice-over clip and segment. It isn't in this public repo because it includes other crews'
choreography (1MILLION at IDL Seoul; the competition waltz).

## Structure (2:58)

| Time | Segment | Source |
| --- | --- | --- |
| 0:00 | Blurred take, song only; "Most people with sight loss see some light and movement. At a dance show, this is often all they get." | `clips_public/live_session7.mp4` 34-44 s blurred + `with_you_im_born_again_slow_waltz.wav` (aligned: song time = take time) |
| 0:10 | Same blur, the take's own audio: Gemini Live's real lines | take 44-64 s |
| 0:30 | Reveal: take 44-64 s sharp, skeleton and captions, plus the "Under the hood, live" panel per line | `live_session7.json` (latency, checker), show `Demo: Andrii, waltz` in Atlas (gaps, rehearsal script) |
| 0:50 | Why (2M+ card) | voice-over `w_why` |
| 1:07 | What Argon prepared from Andrii's rehearsal, from Atlas | `w_notes` |
| 1:37 | Prepared from rehearsal, delivered live (diagram) | `w_live` |
| 1:50 | Crowded competition waltz, couple tracked, everyone else blurred | `data/killtest/waltz-annotated.mp4` 12 s on, `w_world` |
| 2:04 | Where the words go (site waveform), eighteen styles | `w_styles` |
| 2:18 | 20-dancer 1MILLION crew, every dancer tracked, its own narration | `data/killtest/judas-script-annotated.mp4` 66-77 s |
| 2:29 | Open source, for every studio | `w_next` |
| 2:50 | End card | `w_end` |

The voice-over is Gemini TTS (`gemini-3.8-flash-tts`, voice Kore), voiced sentence by sentence and checked against
the script (`speech.speak`). Its text is the `VO` dict in `build2.py`.

## Rebuild

Needs ffmpeg, Chrome (set `CHROME=` to its path if it isn't found) and the repo's `.venv`.

```sh
.venv/bin/python video/build.py     # cards and the older voice-over (c_how, c_end, labels)
.venv/bin/python video/build2.py    # new cards, site crops, the voice-over (skips clips that exist)
.venv/bin/python video/cut2.py clips_public/live_session7.mp4 clips_public/live_session7.json \
    clips_public/with_you_im_born_again_slow_waltz.wav --hook 34
# -> video/work/unseen-steps-demo-v2.mp4
```

To change a voice-over line: edit `VO` in `build2.py`, delete that line's `work/<name>.wav` and `work/<name>-*.wav`,
run `build2.py` then `cut2.py`. Keep it under 3:00 (DeepMind's limit).
