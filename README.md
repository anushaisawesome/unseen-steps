# Unseen Steps

Audio description of dance for blind and partially sighted audiences, built at Encode London (23 to 25 October
2026) by Anusha, Andrii and Nastia.

Professional audio description of dance exists, but only for a performance or two per run at large venues.
Unseen Steps describes a dance the way a trained describer would: it names the steps in the style's own
vocabulary, conveys the dynamics and feeling of the movement, follows formations and soloists in group pieces,
and changes its pace with the music, from calm, spacious lines in a lyrical passage to rapid callouts on the hits
of a chorus. Every line is checked against computer vision measurements of the dancers before anyone hears it.

## How it works

```
music map (librosa)      beats, energy per bar, quiet gaps, strongest hits
pose (YOLO11-pose)       follows the soloist, couple or group; measures jumps, turns, facing, travel, footwork,
                         floor work
glossary (MongoDB Atlas) vetted dance terms per style, with beginner and professional names and translations
        |
Gemini 4 Argon           watches and listens to the whole video with the music map and glossary, and writes a
                         timed script: what to say, when, at what pace and in what tone
        |
checker                  every line's claims (a jump, a turn, going to the floor, travel left or right) must match
                         the pose measurements for the moment it describes; contradicted lines go back to Argon
                         once, otherwise they are dropped
        |
Gemini TTS               speaks each line with a delivery note, time-stretched to fit before the next line; every
                         clip is transcribed to check the voice said only the line
        |
annotated video          skeletons, captions, narration mixed over the music
```

This mirrors how dance audio description is done professionally: a describer prepares a script from a recording,
then delivers it in time with the performance. For a live show, the script comes from the rehearsal recording and
the live pose tracking keeps it in step with the dancers.

## Setup

Needs Python 3.12 and ffmpeg.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # then add your GEMINI_API_KEY, and a MongoDB Atlas connection for the glossary
```

The YOLO pose model downloads on first run and uses an NVIDIA GPU, Apple GPU or CPU, whichever is available.
MongoDB is only needed for glossary terms (`--style`); without it, Argon uses its own knowledge of the style.

## Run it

```sh
scripts/get_demo_clip.sh                                       # a free stock ballet clip with music
.venv/bin/python scripts/killtest.py clips/ballet.mp4 --bars-per-phrase 2 --script
# -> data/killtest/ballet-script-annotated.mp4
```

Options: `--style waltz --terms beginner|professional` uses the vetted glossary and the listener's terminology
level; `--lang uk|de|hi` narrates in another language (lines are checked in English first); `--beats-per-bar 3` for
waltz; `--seed t,x,y` marks who to follow in a crowded clip. Without `--script`, the older pipeline writes one line
per musical phrase with Gemini Flash from the pose features.

## Layout

- `server/scriptwriter.py` Argon's timed script and revisions
- `server/director.py` Argon performance map (style, sections, motifs) and its cross-check against pose
- `server/checker.py` checks each line against the measured movement
- `server/music.py` beats, phrases, quiet gaps, energy, hits
- `server/speech.py` Gemini TTS with delivery notes, read-back check and fit-to-time
- `server/localise.py` translation using dancers' own terms from the glossary
- `server/db.py`, `server/setup_db.py`, `server/glossary_research.py` MongoDB Atlas glossary (Vector Search, Deep
  Research)
- `scripts/killtest.py` pose tracking, features and the annotated video renderer
- `CLAUDE.md` current state and every design decision; `SPEC.md` the original specification

## Deep Research glossary

`server/glossary_research.py` uses the Gemini Interactions API and
`deep-research-preview-04-2026` to build sourced glossary drafts. Deep Research runs in the
background; every job ID is stored under the gitignored `data/glossary-research/` directory so a
closed terminal does not lose the task.

Start and resume an English waltz glossary:

```sh
.venv/bin/python server/glossary_research.py start --style waltz
.venv/bin/python server/glossary_research.py collect INTERACTION_ID --wait
```

Or run the whole English stage, create `gemini-embedding-2` vectors, and upsert only draft terms
into MongoDB:

```sh
.venv/bin/python server/glossary_research.py run --style waltz --import-mongo --embed
```

The parser accepts only sourced HTTPS entries, ignores any status/trust claimed by the model, and
stores English terms as `status: draft` and `trust: pending`. It never overwrites a term already
marked `vetted` or `translated`. English MongoDB imports require `--embed`, preventing a changed
description from keeping a stale vector.

After a dancer has reviewed the English terms in Atlas and marked them `vetted`, research the
names dancers actually use in Ukrainian and German:

```sh
.venv/bin/python server/glossary_research.py run --style waltz --language uk --import-mongo
.venv/bin/python server/glossary_research.py run --style waltz --language de --import-mongo
```

To protect a reviewed localized name from later research runs, set
`translations.<language>.status` to `vetted` in its MongoDB document. Translation jobs refuse to
start until the English records are already `vetted` or `translated`.

Deep Research jobs take minutes, are stored remotely while they run, and may incur agent/search
usage charges. The final terminology and every cited source still require human review before a
term is marked vetted or used in narration.

Use the variable names in `.env.example`. The loader also accepts the legacy local aliases
`Google_Gemini_API_Key`, `MongoDB_URI`, and `MONGODB_USERNAME`, but those aliases should not be
used in new setup files.
