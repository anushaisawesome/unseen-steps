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
- **Following a marked couple (`--seed`): `track_focus` in `scripts/killtest.py`.** Her dress colour
  is followed with CamShift near where it was last seen; a steady focus frame glides around the
  couple and pose runs only inside it (enlarged); skeletons are smoothed and single-frame jumps
  capped. If the dress isn't visible it goes silent, and re-acquires only on the dance floor when
  pose confirms a standing person whose clothes match. Tuned for precision over coverage: it would
  rather say nothing than describe the wrong people. The waltz clip's camera keeps leaving the
  couple, so it's a stress test, not demo footage.
- **Following without a seed (old path):** by clothing colour (HSV histogram), with position as a tiebreak.
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

## Demo footage and ideas (24 Oct, 02:00)

- **Current demo clip:** `clips/ballet.mp4` = Mixkit stock video 956 ("A young ballerina dancing in a
  white room", free Mixkit licence) + librosa's Sugar Plum Fairy excerpt (Kevin MacLeod, CC BY; credit
  it). Render: `python scripts/killtest.py clips/ballet.mp4 --bars-per-phrase 2`. Solo, fixed camera:
  works well, including a visible checker rejection. Andrii's own footage replaces it on Saturday.
- **Planned: upload page.** Anyone uploads a dance clip and picks its style; we narrate it. Guard against
  a wrong style choice: Gemini classifies the style from 3 frames into a fixed list; if it disagrees
  confidently, ask the user ("This looks like ballet, not hip hop. Use ballet terms?"); if unsure, use
  plain descriptions with no style terms. Only the chosen style's vocabulary is offered to the writer.
- **Planned: style glossaries from Deep Research.** Per style: move names, what each looks like in body
  terms (that description is what vector search matches against the phrase's features summary), names in
  uk/de/hi, and source links. Stored in MongoDB `terms`.

## Gemini plan: Argon directs, every model has one job (decided 24 Oct, 02:15)

Why: DeepMind scores 15% on "only possible with Argon" and 50% on using Argon and companion models
effectively with a real verification loop. Flash can describe one phrase; only Argon can hold a whole
performance in one context, find its structure and recurring motifs, and direct the other models.

| Model (all on our key) | Job | Tested? |
| --- | --- | --- |
| `gemini-4-argon` (lead) | **Director.** Watches the whole performance (video + full pose timeline + music map + glossary in one context) and builds the *performance map*: style + confidence, sections, motifs with times, key moments. Live: keeps the show memory in the background and refreshes notes for the writer every few phrases. Uploads: writes the full narration itself. Decides which glossary terms are missing. | Yes: 23 s ballet clip, 3.5 s; found style (0.99), sections, glissade motif at 2.0 s and 5.8 s, 5 key moments |
| `gemini-robotics-er-2-preview` | **Eyes.** Picks who to follow from a description ("the couple in the red dress", "couple number 8"), re-finds them when lost, and checks every few seconds that the tracker is still on them. Fast tracking in between stays CamShift + YOLO. | Yes: boxed the red-dress couple in a crowded frame in 4.4 s, ignoring pink spectators |
| `gemini-robotics-er-2-streaming-preview` | Possible live version of the above | No |
| `gemini-3.8-flash` | Live writer, one line per phrase, using Argon's notes; translation | Yes |
| `gemini-3.8-flash-tts` / `-lite-tts` | Voice (lite may cut live latency) | flash-tts yes, lite no |
| `gemini-3.8-live` | Live voice and ask mode ("what is she wearing?") | No |
| `gemini-3.5-transcribe-live` | Listens to the competition announcer ("Viennese waltz, couple 8") so the song map loads via Atlas Search and Robotics-ER finds couple 8, hands-free | No |
| `deep-research-preview-04-2026` | Glossary: move names, body-terms description, uk/de/hi names, sources, into MongoDB | No (Andrii) |
| `gemini-embedding-2` | Vectors for the glossary, unless Atlas Automated Embedding is used (more MongoDB points) | No |
| `lyria-3.5` | Licence-free music for stock and demo clips | No |
| Later: `antigravity-preview-*`, `gemma-4-*` | Agent that processes uploaded clips end to end; on-device writer for venues without internet | No |

**Verification loops (judges look for these):**
1. Checker: every live line's words must match the measured movement (`server/checker.py`).
2. Argon cross-check: every claim in the performance map ("entrechat at 9 s") must agree with the pose
   data at that time (a jump measured at 9 s); disagreements go back to Argon to revise or drop.
3. Robotics-ER spot-checks that the focus frame is still on the right dancers.

**People stay in control:** the user confirms the style if Argon disagrees with their choice; a describer
can edit the performance map and glossary before the show.

**On screen in the demo:** the performance map panel (sections, motifs), at least one line that calls back
a motif ("the glissade from the opening returns"), the checker badge, and the ER-chosen target.

**Build order (Saturday):**
1. `server/director.py`: Argon performance map + cross-check against pose (Anusha)
2. Robotics-ER target selection: `--target "the girl in the red dress"` replaces `--seed` (Anusha)
3. Writer uses Argon's notes and motif callbacks (Anusha)
4. `scripts/live.py` (both)
5. Glossary via Deep Research into MongoDB (Andrii)
6. If time: announcer transcription, Live ask mode, Lyria music

## Database (MongoDB Atlas)

- Connection string goes in each person's `.env` as `MONGODB_URI` (plus `MONGODB_DB`, default
  `unseen_steps`); names are in `.env.example`. Never commit the string.
- Code lives in `server/db.py`. `python server/db.py` pings Atlas and lists each collection with its
  document count and fields.
- Atlas Network Access must allow the laptop's IP (at the venue, "allow access from anywhere" for the
  weekend, then remove it).
- Planned collections: `terms` (glossary + vector index), `songs` (song maps + Atlas Search on name),
  `show_memory` (Argon's running memory per performance).
