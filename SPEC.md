# Unseen Steps — Project Specification

Live audio description of dance for blind and partially sighted audience members.
Built at Encode London, 23–25 October 2026, by Anusha and Andrii.

> This spec reconciles three sources into one buildable reference: `Ideas/Audio-tracking
> ballroom dancing.md` (the original brainstorm), `README.md` (setup and layout), and the
> Encode London build plan. Where the repo already implements a stage, this spec points at the
> file rather than restating it.

## 1. Overview

Audio description normally covers only one or two performances in a run, and small shows get
none. Unseen Steps describes **every** performance: computer vision tracks the dancer, Gemini
describes the movement, and each line is spoken through earphones in the clean space between
musical phrases, so it never talks over the music. Every line is checked against the measured
movement before it is spoken.

**Named user:** the blind and partially sighted dancers and audiences that Gerard (Andrii's
robotics tutor) works with.

## 2. System architecture

Two processes exchange messages over a WebSocket.

**Browser (`web/`)**
- Plays the song audio to a speaker.
- Runs MediaPipe pose tracking on the fixed venue camera at ~15 landmark frames/sec. (Pose runs
  client-side because the Gemini Live API caps video at 1 fps.)
- Streams landmarks to the server.
- Receives lines with `speak_at` times and **plays the narration through the website itself** —
  the Live voice audio goes into the judges' wired earphones.
- At the reveal, shows the skeleton overlay, a beat counter, and each line appearing at its
  phrase boundary.
- **Hosting is undecided:** run locally or deploy to Vercel. The page is built to work either
  way — the server/WebSocket URL is config-driven, with no hardcoded `localhost`. The choice is
  made before the demo.

**Server (`server/`)**
- Music map (offline), features, writer, checker, voice, database, orchestration (`app.py`).
- Reachable from the web page whether the page is served locally or from Vercel.

**Audio routing & sync — done.** Music plays to both the room speakers and the dancer's
headphones; the website's narration plays to the speakers only. Latency between the Bluetooth
headphones and the speakers is corrected in **VoiceMeeter Banana** by delaying the speaker bus to
match, so the dancer and the room stay on the same beat.

## 3. The live loop (per phrase, ~32 beats / ~15 s)

1. The pose stream sends body points ~15×/sec.
2. At the phrase boundary, `features.py` summarises the phrase.
3. The writer (Gemini 3.8 Flash) drafts a line of ≤8 words, using the vocabulary matches and
   Argon's show memory.
4. The checker passes it, returns it once with a reason for a single retry, or drops it.
5. The Live voice speaks it in the next clean space, 2–4 s after the movement, never on the
   downbeat. If it misses, it moves on only if the next space is close and nothing newer is
   waiting.

**Primary target — single dancer.** The demo is one person (Andrii) dancing, so the pipeline is
tuned for precise single-person move recognition: direction, level, rise, turns, and the quality
of each move.

**Secondary / current test footage — couples.** The footage on hand right now is a couple, so
the system must also handle two bodies, described as a couple (travel, turns, rise and fall, in
hold or apart). Individual claims are made only when both bodies are tracked well. Couple
handling is a robustness/test path, not the demo headline.

## 4. Data contracts

Both builders code to these exact shapes. (See `data/samples/features.json` for worked
examples of the Features shape.)

**Landmarks, per frame**
```json
{"t": 12.40, "people": [{"id": 0, "score": 0.93, "points": [[0.5, 0.4, 0.1, 0.99]]}]}
```

**Features, per phrase**
```json
{"phrase": 7, "start": 98.2, "end": 113.6, "people": 2, "tracking": "good",
 "speed": 0.42, "max_rise": 0.06, "lowest_level": "standing", "travel": "left",
 "turns": 2, "arms_up": 0.3, "stillness": 0.1, "separation": "in hold",
 "summary": "couple travels left with two turns"}
```

**Song** (note `server/music.py` also emits `beats_per_bar` and `beats`)
```json
{"name": "...", "style": "waltz", "bpm": 84, "beats_per_bar": 3,
 "beats": [0.5, 1.2], "phrases": [[0.5, 15.8]], "clean_spaces": [[16.2, 19.1]]}
```

**Vocabulary term**
```json
{"term": "natural turn", "style": "ballroom", "description": "...",
 "names": {"en": "...", "hi": "..."}, "sources": ["url"], "embedding": [0.0]}
```

**Line**
```json
{"phrase": 7, "text": "...", "lang": "en", "verdict": "pass", "reason": null, "speak_at": 114.1}
```

## 5. Components

| Component | File | Owner | Status | Job |
| --- | --- | --- | --- | --- |
| Song map | `server/music.py` | Anusha | **Done** | Offline: beats, 32-beat phrases, clean spaces → `data/songs/<slug>.json` |
| Writer | `server/writer.py` | Anusha | **Done** | Gemini 3.8 Flash drafts a ≤8-word line, vocab-gated, with retry on feedback |
| Pose tracking | `web/` (MediaPipe) | Andrii leads, Anusha helps | To build (MVP) | Tuned for precise single-person moves; two-person tracking as a secondary path |
| Features | `server/features.py` | Andrii | To build (MVP) | Landmark stream → per-phrase features; richer single-dancer detail, couple summary when two bodies present |
| Checker | `server/checker.py` | Anusha | To build (MVP) | Rule-based verification gates (§6) |
| Live voice | `server/voice.py` (Gemini Live) | Anusha | To build (MVP) | Speaks the passed line in the next clean space |
| Orchestration | `server/app.py` | Both | To build (MVP) | WebSocket server wiring the loop together |
| Web playback page | `web/` | Both | To build (MVP) | Plays song + narration, runs pose, renders the reveal |
| Audio routing & sync | VoiceMeeter Banana | Both | **Done** | Music → speakers + dancer's headphones; narration → speakers only; speaker bus delayed to match headphone latency |
| Database | `server/db.py` (MongoDB Atlas) | Andrii | Stretch (Sat) | Vocab vector search, songs, show memory |
| Multilingual | Deep Research + render | — | Stretch (Sat) | Term names in Hindi + one more language, cited |
| Dance summarisation | — | — | Stretch | What went wrong across the whole dance |

> Agree who edits which file before splitting up, to avoid merge conflicts.

### 5a. Uploaded-video style trust and target selection

For an uploaded recording, Gemini first classifies the broad dance style (for example ballet,
ballroom or hip hop) and, where relevant, the ballroom subtype (for example waltz) directly from
representative video frames. It returns a confidence score. The initial trust threshold is **0.90**
(tune it on the evaluation clips rather than treating the number as calibrated forever):

- **At or above 0.90:** select that style's vetted glossary. If the glossary does not exist yet,
  queue Deep Research to build a sourced draft for later human/automatic review; do not block the
  current upload waiting for research.
- **Below 0.90 or mixed/unknown:** use plain observable body language only. For example, say
  "extends one leg behind" rather than guessing "arabesque".
- Passing the style threshold only selects candidate vocabulary. Every technical term must still
  pass the pose/body-signature check and a visual confirmation before it can be spoken.

Target selection happens before tracking:

- With one detected dancer or couple, select them automatically and state who was selected.
- With several dancers or couples, pause on a clear representative frame and draw a numbered
  selectable box around each candidate. A sighted operator can click the person or couple to follow.
- The same choices must be available as descriptive, keyboard- and screen-reader-accessible buttons
  (for example, "Couple 2: red dress and black suit, centre"), with spoken confirmation.
- The selected box seeds the focus tracker. If identity confidence is lost, go silent and request
  reselection rather than silently switching to another dancer.

## 6. Checker rules (the verification loop)

A line passes only if it obeys all of these:
- 10 words at most.
- "jump", "leap" or "lift" need a measured rise.
- "spin" or "turn" need a turn.
- "floor" or "low" need a low level.
- "still" or "pause" need stillness.
- "left" or "right" must match the travel.
- Claims about one dancer need good two-person tracking.

On failure, the checker sends one reason back to the writer for a single retry; if that also
fails, the line is dropped.

## 7. Song handling

- **Option 1 (MVP / demo):** the song is known in advance. Clean spaces are mapped offline with
  `server/music.py` → `data/songs/<slug>.json`. One song for the kill test and demo.
- **Option 2 (stretch):** a database of ≥3 songs. The announced name selects the song table via
  Atlas Search. Needs 3 songs.

## 8. Database (MongoDB Atlas, stretch)

Atlas sits at the core (central to the MongoDB challenge):
- **Vector search** over dance-term embeddings — the vocab match handed to the writer.
- **Atlas Search** over song names — Option 2 song selection.
- **Show memory** (Argon), per performance — a running record of what has already been
  described, so lines don't repeat and the memory panel can be shown at the reveal.

Collections: `terms`, `songs`, `show_memory`.

## 9. Gemini model roles (DeepMind challenge: each doing one job)

| Model | Job |
| --- | --- |
| Argon | Show memory |
| 3.8 Flash | Writer + checker |
| Live | Voice |
| Deep Research | Multilingual term names (Hindi + one more), with cited sources |

Keys and the Atlas connection string live in each person's `.env`, never in the repo.

## 10. Demo (3 minutes, no slides)

### 10a. Opening hook (the cold open, before anything else)
Lead with the problem felt, not explained:
1. Play ~15 seconds of the normal dance clip (clear).
2. Say "What about now?" and replay the **same** fragment heavily blurred.
3. Say "Did you notice the difference? That's how blind people experience it. This is an actual
   problem."
4. If we have it by then, play a **voice note from an actually blind person** (placeholder until
   recorded; falls back to a quote).
5. Then move into the solution.

### 10b. Timing angle
State that this ships **just in time for the release of Google's Intelligent eyewear** — the same
live description running on wearable cameras, not just a venue camera.

### 10c. Main body
After the hook: who it's for → the problem framed → the dancer performs ~60 s with the judges'
eyes closed → the reveal (skeleton overlay, beat counter, lines at phrase boundaries, one
rejected line and why) → what makes it work (the Argon show-memory panel and the MongoDB
dance-term matches) → close (every performance described; next steps with Gerard's dancers and a
training tool for blind dancers).

### 10d. Kit & backup
Speaker, headphone splitter, 2–3 wired earphones, a phone/laptop stand. Backup: recorded clips
through the same system, then a screen recording.

### 10e. Q&A answers
- **Where's the camera?** One fixed venue camera, narration streamed to earphones.
- **Replacing describers?** No — it covers the shows that get none, and describers can add notes.
- **Privacy?** Frames are never stored, only pose points.
- **Wrong lines?** The checker drops anything the movement doesn't support.

## 11. Scope and milestones

- **MVP (tonight, kill test):** music map + pose + features + writer + checker + voice + app +
  web, on one pre-mapped song. Runs tonight against the **couple test footage already on hand**
  (that is what exists now); the demo it builds toward is a **single dancer** with more precise
  move recognition. Kill test at 21:00 — specific, correct lines mean keep going; vague lines mean
  switch to the **backup** (beat-timed dance breakdowns).
- **Saturday, in order:** the live pipeline on one song → Argon show memory + MongoDB
  vocabulary/songs → the Live voice + a second language. Rehearse in the demo spot at 20:00.
- **Sunday 12:00 (hard deadline):** repo with README and setup; a 3-minute demo video on real
  input showing MongoDB in use; a project description (a paragraph per challenge, plus which
  Gemini models we used and how); collect credits (Gemini at the DeepMind booth; the $100 Atlas
  credit at the MongoDB booth).

## 12. Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Lines come out generic | Kill test at 21:00, then the backup idea |
| Close hold confuses pose tracking (couple test footage) | Describe the couple, not individuals |
| No Argon credits until Saturday | Build on Flash, switch when credits land |
| Live demo fails (space, light, WiFi) | Recorded clips, then a screen recording |
| Bluetooth headphone latency throws the dancer off the room's beat | Resolved — VoiceMeeter Banana delays the speaker bus to match; re-check the offset in rehearsal |

The single-dancer demo path avoids the close-hold tracking problem, which is one reason it is the
demo target.

## 13. Privacy & constraints

Frames are never stored, only pose points. Narration goes only to the wired earphones; the music
plays from the speaker. One fixed venue camera.

## 14. Parked (out of scope for the weekend)

Spatial audio, haptics, ask mode, detail dial, groups of 3 or more, dancer feedback. Next after
the weekend: a training tool for blind dancers, with Gerard's haptic-suit idea.

## 15. Sources

- Encode London dashboard — challenges, judging criteria, submission requirements (sign-in needed)
- Encode London on Luma — schedule
- Gemini Live API limits — 1 frame per second video
- RNIB on AI audio description — wanted for coverage, too wordy, human oversight
- Pacific Northwest Ballet — audio dance description
- Amazon patent US11736775 — AI audio description for live events
- Guided Vision in Gemini Live
