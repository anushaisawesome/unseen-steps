# Unseen Steps

Live audio description of dance for blind and partially sighted audience members.

Computer vision tracks the dancers, Gemini describes the movement, and each line is spoken through earphones in the clean spaces between musical phrases, so it never talks over the music. Every line is checked against the measured movement before it is spoken.

Built at Encode London, 23 to 25 October 2026.

## Setup

```
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo 'GEMINI_API_KEY=your_key' > .env
curl -L -o models/pose_landmarker_full.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task
```

## Layout

- `server/` Python server: music map, movement features, line writer, checker, speech
- `web/` page that plays the performance, runs pose tracking and plays the narration
- `scripts/` experiments, starting with the kill test

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
