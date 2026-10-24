# Unseen Steps: notes for Claude

Live audio description of dance for blind audiences, built at Encode London (23–25 Oct 2026) by
Anusha and Andrii. `SPEC.md` is the full specification; this file is the **current state and the
decisions made since**, so read this first. When a decision changes, update this file in the same
commit.

**Hard deadline:** submissions close **Sunday 25 October, 12:00 London time**. Demo video spec:
`docs/demo-video.md`.

## What works now

| Piece | File | State |
| --- | --- | --- |
| Music map: beats, phrases, clean spaces | `server/music.py` | Works. Waltz: `--beats-per-bar 3` |
| Line writer (Gemini 3.8 Flash, JSON output) | `server/writer.py` | Works, ~2–3 s per line |
| Checker (rules: words must match measured movement) | `server/checker.py` | Works |
| Write → check → one rewrite → else silence | `server/narrate.py` | Works |
| Voice (Gemini 3.8 Flash TTS, voice "Kore") | `server/speech.py` | Works, ~2–3 s, lines ~3 s long |
| Translation (checked English → uk / de / hi) | `server/localise.py` | Works, ~2 s |
| Kill test + demo video render on a clip | `scripts/killtest.py` | Works: pose, following, features, lines, voice, skeleton/caption video |
| Who-is-followed contact sheet | `scripts/track_debug.py` | Works |
| Live demo program | `scripts/live.py` | **Not built yet** (see below) |
| MongoDB (vocab, songs, show memory) | — | Andrii, in progress |
| Dance vocabulary + Deep Research translations | — | Andrii, in progress |

Run the kill test / demo render:
```
python scripts/killtest.py clips/waltz.mp4 --beats-per-bar 3 --seed 17,0.42,0.7 [--lang uk]
# -> data/killtest/waltz-annotated[-uk].mp4
```
`--seed time,x,y` marks who to follow (x, y as fractions of the frame). Check it with
`python scripts/track_debug.py clips/<clip>.mp4 sheet.jpg --seed ...` (pink = followed).

## Decisions since SPEC.md

- **Pose: YOLO-pose, not MediaPipe.** MediaPipe found 0–1 dancers per frame on competition
  footage; `yolo11n-pose` found them all. For the live solo demo, a bigger model
  (`yolo11m/l-pose`) on Andrii's laptop at `imgsz=640` is fine if it stays above ~10 fps.
  Sapiens2 was considered and rejected: too heavy to run live.
- **Phrases are 16 beats (4 bars), not 32.** Lines every ~6–8 s; 32 beats was too sparse.
- **Following a couple:** by clothing colour (HSV histogram), with position as a tiebreak.
  People not moving relative to the camera pan, and seated people, are ignored (spectators).
  A missing partner counts as "together" (usually hidden behind the other dancer), and a
  separation must last 1 s and exceed 0.8 body heights.
- **In hold, raised arms and "low" are not events.** The waltz hold is raised arms, and long
  dresses hide ankles (leg length is only trusted when ankles are clearly visible).
- **Directions:** "to the left/right" as the audience sees it. Never "stage left/right" (the
  opposite to a listener).
- **Languages:** the line is written and **checked in English**, then translated by
  `localise.py` with a glossary of dancers' own terms. Demo languages: Ukrainian and German
  (waltz terms are German). The glossary is `{english_term: name_in_language}`, built from the
  vocab collection's `names` field (from Deep Research, not machine translation).
- **Audio routing (live demo):** speaker = music + narration for judges and audience; Andrii's
  headphones = music only. VoiceMeeter Banana delays the speaker bus to match the Bluetooth
  headphone lag. (SPEC.md sections 2, 10d and 13 still mention judges' earphones; that's out of
  date.)
- **Gerard Canal is Anusha's personal tutor** (robotics, KCL), not Andrii's.
- **Before claiming "just in time for Google's intelligent eyewear" in the pitch,** verify it's a
  real announced product.

## Live demo plan (`scripts/live.py`, to build Saturday)

One Python program, no web page or WebSocket needed:
1. Starts the pre-mapped song and the camera together, so every pose frame gets a song time.
2. Follows the biggest moving person near the centre (solo; no clothing tracking needed).
3. At each phrase boundary (known in advance from the song map): features → writer → checker →
   (translate) → voice, reusing `scripts/killtest.py` / `server/` code.
4. Plays the line in the **first clean space after it's ready**; drops it if a newer line is due.
5. Full-screen window for the room: camera feed + skeleton + caption.

Latency: write ~2.5 s + voice ~2.5 s (+ translate ~2 s) after the phrase ends. To get lines out
sooner: start writing ~1.5 s before the boundary, or have the writer return the English line and
its translation in one call (the English is still what gets checked).

## Gotchas

- **The TTS model returns a complete WAV** (header plus a metadata chunk at the end).
  `speech.py` reads the audio out of it; writing the bytes as raw PCM plays the metadata as static.
- `load_dotenv()` with no path breaks when Python reads from stdin; the modules pass the `.env`
  path explicitly.
- Keys (`GEMINI_API_KEY`, Atlas connection string) live in each person's `.env`, never in the repo.
  `clips/`, `models/*.pt`, `data/killtest/` are gitignored.
- The writer's model also sees close-up crops of the dancers; the checker still blocks any word the
  measurements contradict (jump/turn/floor/still/left/right; claims about one dancer need good
  two-person tracking).

## Who owns what

- **Anusha:** music map, writer, checker, voice, translation, live program playback, pitch.
- **Andrii:** pose model on his laptop, features, dance vocabulary, MongoDB, Deep Research
  translations. Pose/features are joint (Anusha helps with tracking).
- Agree who edits which file before splitting up, to avoid merge conflicts.
