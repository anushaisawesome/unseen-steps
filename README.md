# Unseen Steps

Audio description of dance for small studios' own shows, so blind and partially sighted people in the audience
experience the dance, not just the music. Built at Encode London (23 to 25 October 2026) by Anusha, Andrii and Nastia.

**Try it:** https://unseen-steps-studio.vercel.app (17 styles described, a narrated ballet solo, the venue listening page)

**Demo video:** _link to be added_

**A live session, recorded:** [`clips_public/live_session6.mp4`](clips_public/live_session6.mp4) is Andrii dancing
a waltz with `scripts/live.py` narrating him in real time (skeleton, captions, music and voice).

## The problem

Dance is a visual art form, so for the more than two million people in the UK living with sight loss (RNIB), a dance
show is mostly music. Professional audio description of dance exists, but it is expensive and goes to large venues.
The shows put on by small studios, schools and competitions, where most dancers actually perform, never get it. The
project started with Anusha's robotics tutor, Gerard Canal (KCL), who dances ballroom with blind dancers.

## How it works

It works the way a professional describer does: prepare from a recording, then deliver live in time with the show.

**Before the show (Gemini 4 Argon).** The studio uploads a rehearsal video. Argon watches and listens to the whole
piece in one context (5 frames a second, with its music) and builds a map: the style and its influences with visible
evidence, sections, formations and canons, the piece's signature, every change of texture and energy, and the key
moments. It re-watches each section at 8 frames a second and writes show notes and a timed script the way an expert
describer would, in the style's own vocabulary explained for newcomers. A second Argon pass reviews it as a dancer
would hear it, and every line is checked against the video at its moment (10 frames a second). The song is mapped
into beats, phrases and the quieter gaps where a line fits. The notes are stored per show in MongoDB Atlas.

**On the night (Gemini Live).** A camera follows the dancer and YOLO11 pose tracking measures jumps, turns and their
direction, facing, footwork, floor work and turnout. One Gemini Live session holds the show notes, sees the camera at
2 frames a second, and at each gap in the song describes what the dancer actually does now, including anything
different from rehearsal, starting to speak in under a second. A checker compares every claim with the measured pose;
if a line was wrong, the next one puts it right.

**People stay in charge.** The studio, or a describer working with it, reads and edits the show notes before the show
(`scripts/edit_show.py`); the live narration uses exactly what was saved.

## Reading the real world honestly

- **Verification loops.** Pose checker on every live line (turns, jumps, floor work, stillness, directions, turnout
  for plié and ballet positions); per-line visual check of every prepared line against its moment; every recorded
  voice clip is transcribed and must say exactly its caption, or it is re-recorded or dropped.
- **Messy inputs.** Keypoints the pose model isn't confident about (under 0.3) are left out of the measurements, and
  turnout and leg length are measured only when hips, knees and ankles are clearly visible (0.5; long dresses hide
  ankles). A measurement that can't be made (in a group, or an unmeasurable rotation) skips its check rather than
  guess. In crowded recorded footage the tracker would rather go silent than describe the wrong person.
- **Uncertainty.** A technical term is used only when every part of its definition is visible; live, a figure is
  named only if the routine contains it and it is clearly seen, otherwise the body is described. Style influences are
  named only with several distinct visible cues.
- **Privacy.** Live, camera frames go to Gemini and are not stored unless the studio chooses to record the session.
  In rendered videos, everything outside the dancers being described (spectators, other couples, judges) is
  blurred.
  Narration goes to each listener's own earphones, never over the room's music. Clips of other people's
  choreography are never put in this repository: the style demos read public YouTube links directly and play them in
  YouTube's own player.

## Models and data sources

| Model | Job |
| --- | --- |
| `gemini-4-argon` | Performance map, section zoom, show notes and timed script, second-describer review, per-line visual check, style check, final cut; running notes during a live show |
| `gemini-3.8-live` | Live narration from the camera and the show notes (audio out, ~0.8 to 1 s to first sound) |
| `gemini-3.8-flash-tts` | Voice for recorded narration |
| `gemini-3.8-flash` | Checks each voice clip against its caption; translation; regression judging |
| `gemini-embedding-2` | Glossary vectors for Atlas Vector Search |
| `deep-research-preview-04-2026` | Sourced glossary drafts (reviewed by dancers before use) |
| `gemini-3-pro-image` | The logo and the site illustration |
| YOLO11 pose (Ultralytics) | Body tracking and measurements; librosa for the music map |

Data: rehearsal and live recordings of Andrii (our own); public YouTube performances read by Gemini directly (credited
on the demo page; not downloaded); a Mixkit stock ballet clip (free licence) with Kevin MacLeod's "Dance of the Sugar
Plum Fairy" (CC BY 4.0); a waltz glossary from Deep Research with its cited sources, vetted by dancers; sight-loss
figures from RNIB.

MongoDB Atlas holds the dance glossary (canonical and beginner names, plain descriptions, translations, sources,
review status; `$vectorSearch` over 3072-dimension vectors, filtered by style) and each show's notes, map, gaps and
rehearsal script.

## Setup

Needs Python 3.12 and ffmpeg.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # add your own GEMINI_API_KEY, and a MongoDB Atlas connection
```

On Windows (PowerShell): `py -3.12 -m venv .venv`, then `.venv\Scripts\pip install -r requirements.txt`,
`Copy-Item .env.example .env`, and run the scripts with `.venv\Scripts\python`. Install ffmpeg (for example
`winget install ffmpeg`) and make sure it's on the PATH.

The YOLO pose model downloads on first run (NVIDIA GPU, Apple GPU or CPU).

MongoDB Atlas, once your connection is in `.env`:

```sh
.venv/bin/python server/setup_db.py   # once: collections plus the vector and text search indexes (idempotent)
.venv/bin/python server/db.py         # check: prints "connected to 'unseen_steps'" and the collections
```

Search indexes need an Atlas cluster (not a plain local MongoDB) and take a minute or two to build.

## Run it

A show, start to finish:

```sh
# 1. Before the show: show notes from the rehearsal video, stored in Atlas
.venv/bin/python scripts/prepare_show.py --name "My show" --rehearsal rehearsal.mp4 --song song.mp3 --style waltz --beats-per-bar 3
# 2. Optional: read and edit the notes
.venv/bin/python scripts/edit_show.py "My show"
# 3. On the night: camera 0, the same song; --record saves the session and a log of every line
.venv/bin/python scripts/live.py --show "My show" --song song.mp3 --camera 0 --beats-per-bar 3 --style waltz --record night.mp4
```

Other entry points:
- `scripts/youtube_demo.py`: describe public YouTube performances for the style demo page (`web/youtube-demo/`).
- `scripts/killtest.py clips/ballet.mp4 --script`: a narrated, annotated video of a local clip with the skeleton drawn.
- `scripts/regress.py`: the regression list of a dancer's must-haves from `feedback/`.
- `web/`: the site (static pages plus two Python functions on Vercel).

## Layout

- `server/director.py` Argon's performance map, section zoom and style check
- `server/scriptwriter.py` the dancer's-eye brief, windowed writing, review, per-line verification, final cut
- `server/show_notes.py` show notes from a rehearsal; `scripts/prepare_show.py`, `scripts/edit_show.py`
- `scripts/live.py` the live program (camera, song, pose, Gemini Live, checker, recording)
- `server/checker.py` checks claims against the measured movement
- `server/music.py` beats, phrases, quiet gaps, energy, hits
- `server/speech.py` voice with the caption check and fit-to-time
- `server/db.py`, `server/setup_db.py`, `server/glossary_research.py` MongoDB Atlas glossary and shows
- `feedback/` a dancer's reviews of the narration, read by Argon on every run
- `CLAUDE.md` every design decision; `SPEC.md` the original specification and room for improvement

## What's next

Unseen Steps is open source under the MIT licence (`LICENSE`), so any studio can run it for its own shows. Next: a show-notes editor in the browser,
testing with blind audiences at real recitals (starting with Gerard's dancers), live tracking for whole groups, and a
training tool for blind dancers.

The Deep Research glossary pipeline is documented in `server/glossary_research.py`.
