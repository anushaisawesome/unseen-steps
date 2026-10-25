# Unseen Steps: notes for Claude

Live audio description of dance for blind audiences, built at Encode London (23–25 Oct 2026) by
Anusha and Andrii. `SPEC.md` is the full specification; this file is the **current state and the
decisions made since**, so read this first. When a decision changes, update this file in the same
commit.

**Result (25 Oct, finale):** Unseen Steps won the **Google DeepMind Special Prize for Open Innovation** ($2,000 in Google Cloud
credits). The project is MIT open source; keep it that way and keep the README, site and docs public-ready.

**Standing rule for every Claude on this repo:** anything Anusha and Andrii decide or discuss goes into this file in the same session, so the other person's Claude has it after `git pull`.

**Result (25 Oct, finale):** not in the top 10 pitches, but **Google DeepMind created a Special Prize for Open
Innovation for Unseen Steps** ($2,000 in Google Cloud credits). Details at the end of this file. The hackathon is over;
the deadline notes below are history.

**Hard deadline (passed):** submissions closed **Sunday 25 October, 12:00 London time**. Demo video spec:
`docs/demo-video.md`.

> **ANDRII: Claude's reference cut of the demo video (25 Oct ~09:15).** `unseen-steps-demo-final.mp4` (2:58) and a
> `work.zip` of every card, voice-over clip and segment are in the PRIVATE clips repo release `video-1`:
> https://github.com/anushaisawesome/unseen-steps-clips/releases/tag/video-1 (`gh release download video-1 -R
> anushaisawesome/unseen-steps-clips`). Not in this repo: it includes other crews' choreography. Structure, sources and
> rebuild commands: `video/README.md`. Built from session 7 (34-64 s), `live_session7.json` and the song; session 8
> isn't needed. Keep the final under 3:00.

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
| Live demo program | `scripts/live.py` | Works: Gemini Live, about 0.8 s to first sound (see below) |
| MongoDB (vocab, songs, show memory) | `server/db.py`, `server/setup_db.py` | Connected; collections and search indexes ready |
| Dance vocabulary + Deep Research translations | `server/glossary_research.py` | Latest run produced 20 validated Waltz drafts; terminology confirmation belongs to Anusha + Nastia |

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
- **Uploaded-video style trust:** Gemini classifies the broad dance style and, for ballroom, its subtype
  from representative frames. At confidence >= 0.90 the system may use that style's vetted glossary;
  below 0.90 or for mixed/unknown styles it uses plain observable body language only. Style confidence
  selects candidates but never replaces the per-term pose and visual checks.
- **Uploaded-video target selection:** one dancer/couple is selected automatically. If several are found,
  pause on a representative frame with numbered clickable boxes; expose the same choices as descriptive
  keyboard/screen-reader buttons. The selected box seeds the tracker; if identity is lost, go silent and
  ask for reselection rather than switching people.
- **Terminology level and aliases:** each move has one canonical professional name plus vetted common or
  beginner aliases. The listener chooses `beginner` or `professional` terminology; never infer expertise
  from the video. Recognition searches every alias, while narration uses the chosen display name. Anusha
  and Nastia jointly confirm Waltz names and their syllabus/region context before a term becomes `vetted`.

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

- **Anusha:** music map, writer, checker, voice, translation, Argon director, Robotics-ER targeting, live
  program playback, pitch; jointly confirms glossary terminology with Nastia.
- **Andrii:** pose model on his laptop, Deep Research/MongoDB glossary pipeline, filming the demo footage,
  audio routing.
- **Nastia (joined Sat 24 Oct, morning; GitHub `nxstiaa`):** Imperial, bioscience, computer vision in medicine. Works with
  Anusha on **computer vision quality**: an evaluation set, keypoint filtering, joint-angle features, pose
  signatures for glossary terms, model benchmark for live. **Also has design experience: leads the design of the live venue page and the
  upload page** and jointly confirms glossary terminology with Anusha (accessibility requirements below). Onboarding: `docs/ONBOARDING.md` and the shareable doc
  https://claude.ai/artifact/EPUve2GLzGbzjPyf8zVGmm.
- Agree who edits which file before splitting up, to avoid merge conflicts. Computer vision code currently
  lives in `scripts/killtest.py`; if Nastia and Anusha both work on it, split it into `server/pose.py`
  (tracking) and `server/features.py` (features) first.

## Demo footage and ideas (24 Oct, 02:00)

- **Current demo clip:** `clips/ballet.mp4` = Mixkit stock video 956 ("A young ballerina dancing in a
  white room", free Mixkit licence) + librosa's Sugar Plum Fairy excerpt (Kevin MacLeod, CC BY; credit
  it). Render: `python scripts/killtest.py clips/ballet.mp4 --bars-per-phrase 2`. Solo, fixed camera:
  works well, including a visible checker rejection. Andrii's own footage replaces it on Saturday.
- **Planned: upload page.** Anyone uploads a dance clip; Gemini classifies the broad style (ballet,
  ballroom, hip hop, etc.) and any relevant ballroom subtype from representative frames. Confidence >=
  0.90 unlocks that style's vetted glossary as candidate vocabulary. Below 0.90 or for mixed/unknown
  footage, narration uses plain body descriptions only. Deep Research may top up a missing glossary in
  the background but never delays the current upload.
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

**People stay in control:** the detected style, confidence and selected target are shown/spoken back; a
sighted operator can correct the target or style label, and a describer can edit the performance map and
glossary before the show. Corrections do not bypass the per-term verification checks.

**On screen in the demo:** the performance map panel (sections, motifs), at least one line that calls back
a motif ("the glissade from the opening returns"), the checker badge, and the ER-chosen target.

**Build order (Saturday):**
1. `server/director.py`: Argon performance map + cross-check against pose (Anusha)
2. Robotics-ER target selection: `--target "the girl in the red dress"` replaces `--seed` (Anusha)
3. Writer uses Argon's notes and motif callbacks (Anusha)
4. `scripts/live.py` (both)
5. Glossary via Deep Research into MongoDB (Andrii); terminology confirmation (Anusha + Nastia)
6. If time: announcer transcription, Live ask mode, Lyria music

## Database (MongoDB Atlas)

**Status (24 Oct, 02:40):** free M0 cluster `unseen-steps` (AWS Paris) in the **Unseen Steps** project of the
**Unseen Steps** Atlas organisation. Database name `unseen_steps`. Anusha is connected; no collections yet.

**Andrii, to connect (do this once, in order):**
1. In Atlas, switch to the Unseen Steps organisation and project.
2. **Database Access → Add New Database User**: create *your own* user and password (don't reuse
   Anusha's). Role: "Read and write to any database" (or Atlas admin) is fine for the weekend.
3. **Network Access → Add IP Address → Add Current IP Address** (or "Allow access from anywhere" for the
   weekend only; remove it after).
4. Copy `.env.example` to `.env` if you haven't, and fill in:
   ```
   MONGODB_USER=<your database user>
   MONGODB_PASSWORD=<your database password>
   MONGODB_HOST=unseen-steps.mp9b0or.mongodb.net
   MONGODB_DB=unseen_steps
   ```
   (Or set a single `MONGODB_URI=mongodb+srv://...` instead of the three parts.)
5. Test: `python server/db.py` should print `connected to 'unseen_steps'` and list collections.

**Gotchas:**
- Never commit `.env` or paste the password into chat or docs. Each person has their own database user.
- If `.env` is open in TextEdit while something else edits it, TextEdit can save its old copy back over
  it. Close the editor window without saving after any automated change.
- Free tier allows up to 3 Atlas Search / Vector Search indexes in total, so plan: one vector index on
  `terms`, one search index on `songs`, one spare.

**Collections to create (shapes match `SPEC.md` section 4):**
- `terms`: the glossary, one document per move:
  `{"term": "natural turn", "style": "waltz", "aliases": ["right box turn", "right turn box"],`
  `"display_names": {"professional": "natural turn", "beginner": "right box turn"},`
  `"description": "couple rotates right while travelling", "names": {"en": "natural turn", "uk": "...",`
  `"de": "..."}, "sources": ["url"], "embedding": [...]}`.
  The `description` (what the move looks like in body terms) is what vector search matches against each
  phrase's features summary, so write it in plain body language. Vector index on `embedding`
  (`gemini-embedding-2`, or Atlas Automated Embedding on `description` for extra MongoDB points).
- `songs`: song maps from `server/music.py` (`name`, `style`, `bpm`, `beats`, `phrases`, `clean_spaces`),
  with an Atlas Search index on `name` so an announced dance name finds its map.
- `show_memory`: Argon's running memory, one document per performance.

**Next code (Anusha):** lookup functions in `server/db.py` (`match_terms(summary, style)`,
`find_song(name)`, `save_memory(...)`), then the writer reads real vocabulary from `terms`.

**If time (25 Oct, before the demo video):**
- [ ] **Atlas Search with `find_song(name)`.** Only Atlas Vector Search is used today (`match_terms`). The `song_name`
  search index on `songs.name` exists and is READY (`server/setup_db.py`), but no code runs `$search`. Add
  `find_song(name)` to `server/db.py` (`$search` with fuzzy text on `name`, so "viennese waltz" finds its map), use it
  where a song map is loaded, and show it in the demo video's MongoDB section. Not used: Hybrid Search, Automated
  Embedding, Stream Processing, Voyage AI.

## Demo priorities (decided 24 Oct, 02:50)

1. **Headline: live real-time narration of Andrii dancing** (`scripts/live.py`). This is the "blow their
   socks off" moment and gets built first on Saturday. The style is known in advance (his dance), so no
   style guessing is needed live.
2. **Second act: the upload page.** A judge films Andrii (or anything) on their own phone, uploads it, and
   gets a narrated video back in about a minute. Reuses the `scripts/killtest.py` pipeline wrapped in a
   function, behind a small FastAPI server and page, run locally on the laptop.

### Upload page flow
1. **Upload checks first** (Gemini on a few frames): is there dancing; how many dancers (1–2 fine; a crowd
   means Robotics-ER asks "who should I follow?"); length cap 3 min; is there music (if not, fixed 6 s
   phrases instead of the music map).
2. **Argon classifies the style per section**, with the evidence and confidence spoken and shown ("ballet,
   94%: pointe shoes, tutu, turnout"). At >= 0.90 use that style's vetted glossary as candidate vocabulary;
   below 0.90 or for mixed/unknown footage use plain body terms only. A fixed-list correction control is
   available to a sighted describer, but it does not bypass the confidence or per-term safety checks.
3. **Argon builds this video's performance glossary** (moves, times, body-terms descriptions), reusing
   MongoDB `terms` and saving new ones. Deep Research tops terms up with sources in the background (too slow
   per upload).
4. Pipeline: music map → pose → features → writer → checker → voice → video with skeleton and captions.
5. Uploads are deleted after processing; faces of everyone except the followed dancers are blurred.

### Input sanitising: confidence gate plus per-term verification
Style confidence is the first gate: only a classification at or above 0.90 may select a style-specific
glossary. Below that threshold, narration uses plain body language. Passing the style gate is still not
enough to speak a technical term because confidence numbers are not perfectly calibrated and pieces mix styles:
- Terms from the high-confidence style are allowed into the candidate list.
- **Every dance term must pass two checks before it's spoken:** (1) a body-shape check against the pose data
  (e.g. arabesque: one leg extended behind, standing leg straight; store a `signature` per term), and (2) a
  visual check, a second Gemini call on the frame at that moment: "Is she doing an arabesque? yes/no".
- If either fails, drop the term and describe the shape plainly ("balances on one leg, the other stretched
  behind"). A wrong style label then can't put a wrong term in anyone's ear.
- "Not sure / mixed" or confidence below 0.90 means plain descriptions only; no technical terms.

## Glossary pipeline (decided 24 Oct, 03:00)

How the `terms` collection gets filled, with Anusha and Nastia confirming terminology before anything is
translated:

1. **Deep Research builds a skeleton glossary of ballroom terms in English** (start with Waltz, since that's
   the live demo). For each term: canonical professional name, common/beginner aliases, style, a plain
   body-language `description` of what it looks like
   (written for Gemini and the pose data, e.g. "couple in closed hold rotates clockwise while travelling
   along the line of dance"), a `signature` (the body-shape rule the pose check tests), and `sources`.
   Status `draft`.
2. **Anusha and Nastia jointly confirm every Waltz term and alias:** one reviews the professional and
   common/beginner names; the other double-checks them, including International/American/social syllabus
   context where relevant. Fix, qualify or delete anything wrong. Mark `status: "vetted"` and record both
   names in `vetted_by`. Nothing unvetted is used in narration.
3. **Only after vetting: Deep Research again, once per language** (Ukrainian, German; Hindi later), pulling
   the names dancers actually use from dance blogs, federation syllabi and teaching material in that
   language, for nuance. Never machine translation. Store `names.<lang>` and per-language `sources`;
   status `translated`.
4. The writer only gets vetted terms. It receives the listener's explicit `terminology_level` and speaks
   `display_names.professional` or `display_names.beginner` accordingly; the setting never changes the
   recognized move. `localise.py` gets the vetted names per language as its glossary.

Suggested document fields: `term, style, aliases, display_names {professional, beginner}, naming_context,
description, signature, names {en, uk, de, ...}, sources {en: [...], uk: [...], de: [...]}, status
(draft | vetted | translated), vetted_by, embedding`.

### Deep Research implementation status (24 Oct)

- `server/glossary_research.py` starts and resumes `deep-research-preview-04-2026` jobs through the
  Interactions API, validates one final JSON block, rejects placeholders/search pages/forums/document
  mirrors, and stores generated files under gitignored `data/glossary-research/`.
- A real English waltz run completed: 17 sourced draft terms survived validation. Three terms were rejected
  because their only sources were Scribd/forums; one-source terms are flagged for extra review.
- English Mongo imports require `gemini-embedding-2` vectors (3072 dimensions). All 17 waltz drafts are now
  in Atlas with embeddings; the vector and song-name search indexes report `READY`. Imports atomically protect
  `vetted`/`translated` terms and translations marked vetted per language.
- Andrii initially expert-vetted `reverse turn` from five years of ballroom experience. It is stored with aliases
  `left box turn` / `left turn box`; `natural turn` has `right box turn` / `right turn box`. The Gemini
  spending cap blocked the new reverse-turn embedding, so that one record is marked `pending_billing_cap`.
  Ongoing terminology confirmation has now moved to Anusha and Nastia.
- Ukrainian/German jobs refuse to start until English terms exist in MongoDB with status `vetted` or
  `translated`. A localized name can be protected from later reruns by setting
  `translations.<lang>.status` to `vetted`.

## Other dance styles: trust levels (decided 24 Oct, 03:05)

Gemini runs every style end to end; a human expert only raises the ceiling.

| Level | Styles | How terms get in | When a term is spoken |
| --- | --- | --- | --- |
| `vetted` | Ballroom (Anusha + Nastia review) | Deep Research, then both reviewers confirm canonical and common names | When the pose and visual checks pass |
| `auto` | Everything else (ballet, hip hop, contemporary...) | Deep Research, kept only if 2+ independent sources agree on the term and its description, and Argon's own understanding matches | Only when style confidence is >= 0.90 and both term checks pass; otherwise plain description |
| none | Unknown style or "Not sure / mixed" | No terms | Plain body-language description only |

- Plain descriptions work for any dance with no glossary at all; terms are a bonus layer, so unvetted
  styles get fewer technical names, never worse narration.
- Later: an expert review page (any teacher or describer approves/fixes terms for their style, recorded in
  `vetted_by`), and listener flags ("that term was wrong") that demote a term to `auto` for review.
- Pitch line: "Gemini does the whole job for any style; where a human expert has checked the glossary, you
  get richer, more precise language."
- Store the level on each term as `trust: "vetted" | "auto"`.

## Choosing who to follow, and accessibility (decided 24 Oct, 03:10)

**Pick the dancers from a representative frame.** If one dancer/couple is found, select them automatically.
If several are found, show a paused frame with a numbered selectable box around each candidate; a sighted
operator clicks the person or couple to follow. The exact same detections are exposed as descriptive,
keyboard- and screen-reader-accessible buttons ("Couple 2: red dress and black suit, centre") and read back
by TTS for confirmation. `gemini-robotics-er-2-preview` initializes the chosen box and the fast tracker keeps
the focus frame around that target. Narration is only about the selected dancer/couple. If identity confidence
is lost, go silent and ask for reselection rather than silently switching to someone else.

**The web app must be properly accessible (it's an accessibility tool):**
- WCAG 2.2 AA as the bar. Semantic HTML, full keyboard use with visible focus, no information by colour
  alone, good contrast, respects reduced motion.
- Screen readers: real `<label>`s on every field; an ARIA live region (`aria-live="polite"`) for progress
  ("Watching the dance... 40%") and for each narration line as it's spoken; focus moves to the result when
  it's ready.
- **Dictation for every field** with `gemini-3.5-transcribe` (press and speak), with the same text box as a
  fallback. Spoken confirmations with Flash TTS.
- Output a **WebVTT descriptions track** (`<track kind="descriptions">`) and a plain-text transcript, so the
  narration works in any player and with any screen reader, not just our page.
- Test with VoiceOver (Mac) before the demo.

**How blind and partially sighted people will upload** (screen readers: VoiceOver, TalkBack, JAWS, NVDA):
- One big, clearly labelled **native** button, "Choose or record a dance video": `<input type="file"
  accept="video/*">`. It opens the phone's own picker (Photo Library / Take Video / Choose File), which
  screen readers handle well. **Never a drag-and-drop-only area** (unusable without sight or a mouse).
- Read back what was chosen: file name and length ("Waltz final, 1 minute 32"), then spoken progress.
- **Share sheet route:** make the page an installable web app with a share target, so a video from WhatsApp
  or Photos can go Share → Unseen Steps. Works on Android; iPhone likely doesn't support web share targets
  (from memory, unverified), so the native picker is the iPhone route.
- "Paste a link" for direct video file links only (not YouTube/Instagram, whose terms forbid downloading).
- Key user: blind dancers reviewing recordings of their own performances (filmed by a coach or parent),
  which ties to the training-tool next step.

This also deepens the Gemini use: transcription for dictation, Robotics-ER for choosing and confirming the
target, TTS for spoken confirmations, Argon for the performance map, Flash for lines.

## Accessibility review: what changed (24 Oct, 03:25)

Realistic problems with the first plan, and the fixes. This **replaces** the earlier plan where they differ.

Problems: too many steps for screen reader users; **custom dictation duplicates the OS dictation** blind users
already use (and needs mic permission, can clash with screen reader gestures), so **drop it**; free-text
"who to follow" assumes the user knows what's in the video; asking the style is a burden; the live venue page
was undesigned and **"scan the QR code" is a visual task**; no control over amount or speed of narration
(many screen reader users listen at 2–3x); partially sighted users (most people registered blind) were forgotten.

**Live venue page (most important):**
- Getting in without sight: a short URL the announcer reads out (e.g. "unseensteps.live/hall"), plus QR, an
  NFC tag on the seat or programme, staff help, and a link in the ticket email.
- One big "Start listening" button. Keeps playing with the screen locked (Media Session API, lock-screen
  controls), reconnects automatically, remembers settings.
- Settings: language, brief / detailed, speech speed.

**Upload page (one action, sensible defaults):**
1. One labelled native button "Choose or record a dance video" (+ Android share target).
2. Only if there are several dancers: show a representative frame with numbered clickable boxes. Expose the
   same candidates as descriptive buttons for keyboard/screen-reader users ("1. Red dress and black suit,
   centre. 2. Yellow dress, left. 3. Everyone"). No free text: also closes the injection risk.
3. Style detected automatically and shown with confidence ("Style: waltz, 94% detected"). At >= 0.90 the
   vetted style glossary is eligible; below 0.90 or unsure/mixed means plain descriptions. A "Change" control
   is available for sighted describers but cannot bypass the term-verification checks.
4. Progress announced only at milestones via a polite live region; focus moves to the result when ready.
5. Result controls: language, brief / detailed, speech speed, **"Pause the video for descriptions"**
   (extended audio description, the standard for recorded media), separate narration volume, transcript and
   WebVTT descriptions download, keyboard shortcuts (space = play/pause).

**Partially sighted:** large adjustable captions, high contrast, reflow at 400% zoom, bold skeleton overlay.

**Testing:** VoiceOver (iPhone) and TalkBack (Android) before the demo; ideally 10 minutes with one blind
user (one of Gerard's dancers). **Pitch:** 10 seconds of the page driven by VoiceOver.

## Saturday task lists (written 24 Oct, 03:35; superseded 14:55)

**The live team to-do list (Anusha, Andrii, Nastia, with checkboxes) is now the shared doc
https://claude.ai/artifact/RvPoVfKk2fmu9pDPwcUSR4.** Schedule: parallel work until 16:30, sync at 16:30,
render the demo clip, submit checkpoint 2 at 17:45, live program 18:00–20:00, rehearsal 20:00. The lists below
are the original overnight version, kept for context.

**Deadlines:** checkpoint 2 on the Encode platform by **Sat 18:00** (code link, description, bounties,
problem and who it's for, live demo). Rehearsal in the demo spot **Sat 20:00**. Final submission **Sun 12:00**.

### Andrii
1. **Setup (15 min):** `git pull`; `pip install -r requirements.txt`; `.env` with your own Gemini key and your
   own Atlas database user (see "Database"); `python server/db.py` should say connected.
   `scripts/get_demo_clip.sh`, then `python scripts/killtest.py clips/ballet.mp4 --bars-per-phrase 2` to check
   the whole pipeline runs on your laptop. Pose now picks NVIDIA GPU / Apple GPU / CPU automatically, and
   downloads the YOLO model on first use.
2. **Pose speed on your laptop:** try `yolo11m-pose.pt` and `yolo11l-pose.pt` on your webcam at `imgsz=640`;
   keep the biggest one that stays above ~10 fps. Pass it with `--model`. This decides the live demo setup.
3. **Film yourself (morning, needed for checkpoint 2):** fixed camera on a stand, whole body in frame, 3–4 m
   back, decent light, your demo song playing out loud, 60–90 s, two takes (one with big clear moves).
   Put the files in `clips/` and tell Anusha.
4. **Your demo song:** the audio file, then `python server/music.py <file> --name "<song>" --style waltz
   --beats-per-bar 3`; that map goes into the `songs` collection.
5. **Glossary step 1:** Deep Research for the English waltz skeleton glossary (fields in "Glossary pipeline"),
   saved to MongoDB `terms` as `draft`. Then **vet every term** and mark them `vetted`.
6. **Glossary step 2 (after vetting):** Deep Research per language (Ukrainian, German) from dancer sources.
7. **Audio routing:** re-check VoiceMeeter (music to speaker + your headphones, narration to speaker only) at
   the 20:00 rehearsal.
8. `SPEC.md`: point readers to this file for decisions since, or fix the out-of-date parts (Gerard is
   Anusha's tutor; YOLO not MediaPipe; 16-beat phrases; narration to the speaker, not judges' earphones).

### Anusha
1. **Checkpoint 2 (by 18:00):** submit on the platform with the repo link, description, bounties (DeepMind,
   MongoDB, The Real World), problem and who it's for, and a demo clip: `ballet-annotated.mp4` now, Andrii's
   footage once rendered.
2. **`server/director.py`:** Argon performance map (style, sections, motifs, key moments) plus the cross-check
   of every claim against the pose data.
3. **Robotics-ER target selection:** list the dancers it sees as choices; follow the chosen pair; say who it
   picked.
4. **Writer upgrades:** use Argon's notes and motif callbacks, and vetted terms from MongoDB
   (`match_terms`, `find_song`, `save_memory` in `server/db.py`, plus the vector index on `terms`).
5. **`scripts/live.py` with Andrii (the headline):** camera + song together, pose, phrase boundaries,
   features → writer → checker → voice, full-screen skeleton and captions. Start writing ~1.5 s before each
   boundary to hit the clean space.
6. At the booths: collect the $100 Atlas credit (MongoDB) and Gemini credits (DeepMind; ask Amit or
   Geneviève about Robotics-ER streaming for live tracking).
7. **Sunday 08:00–11:00:** demo video per `docs/demo-video.md`, README, submission text. Submit by 12:00.
8. Upload page and live venue page only after `live.py` works.

## Pose model candidates considered (24 Oct)

- **SAM-Body4D** (arXiv 2512.08406, github.com/gaomingqi/sam-body4d), suggested by Nastia: training-free 4D
  body-mesh recovery from video (SAM 3 tracking + diffusion occlusion fill + SAM 3D Body), identity-consistent,
  handles occlusion and crowds. **Not for this weekend and never for live:** tested on an A100 80 GB, no frame
  rate reported, explicitly not real time, no quantitative comparison with standard pose models, three large
  models to install. Worth it later for the **upload path on a cloud GPU**: true 3D body orientation would fix
  turn counting (our noisiest feature), and SAM 3's text-prompted tracking (from memory, check) fits "follow the
  girl in the red dress". Roadmap line for the pitch.
- **Sapiens2:** rejected Friday, too heavy to run live.
- **Live demo stays on YOLO-pose** (`yolo11n/m/l-pose`, pick the biggest that holds 10+ fps on the demo laptop).
- **Andrii's laptop has an RTX 4070 (laptop card: 8 GB VRAM).** Order of work on it:
  1. Benchmark `yolo11n/m/l/x-pose` at `imgsz=640` on his webcam and our clips; pick the biggest holding ~15 fps
     (likely `l` or `x`). That's the live model: a big accuracy gain over the `n` model used on the Mac.
  2. Optional, **timeboxed to 30 min:** SAM 3 alone (text-prompted tracking) on a 10 s clip for the crowded
     upload path. Drop it if it doesn't install cleanly or runs out of memory.
  3. Full SAM-Body4D (with the diffusion model) probably won't fit in 8 GB; leave it for a cloud GPU later.
- **SAM-Body4D tried and dropped for the weekend (Sat 16:00):** it failed on Nastia's setup, and won't run on
  Anusha's Mac either. Their own profile (H800 80 GB): single target, 100 frames = **14.5 GB peak GPU memory**,
  0.7 s/frame; 5 targets = 41–53 GB. CUDA-only (cu118 PyTorch + detectron2), no CPU/Mac mode. So it doesn't fit a
  laptop 4070 (8 GB) or a 16 GB Mac. Possible later on a 24 GB+ cloud GPU (A100/L4) with
  `completion.enable = false`. Don't spend more time on it this weekend.
- **SAM-Body4D runs on Colab Pro (Sat 18:00, Nastia):** `scripts/sam_body4d/sam_body4d_ballet.ipynb` (A100,
  Run all, ~30 min) on the clean ballet footage (Mixkit 956, 24 fps, same frames as `docs/media/ballet-demo.mp4`).
  Result: a 3D body mesh in **all 547 frames**; pose matches the footage. Depth (distance from camera,
  ~3.4–5.2 m) jitters frame to frame, so floor position is noisy; body shape and orientation are steadier.
  Viewer: `docs/media/ballet-3d.html` (3D body synced with the YOLO demo and SAM-Body4D's own render), rebuilt with
  `python scripts/sam_body4d/build_viewer.py <results.zip> docs/media/ballet-demo.mp4 <out.html>`
  (needs `numpy imageio-ffmpeg`). The notebook is generated by `make_nb.py`; edit that, not the `.ipynb`.
  Colab gotchas it handles: Colab is Python 3.13 but SAM 3 pins `numpy==1.26`, so it uses a micromamba
  Python 3.12 env; Detectron2 built without its CUDA ops (`CUDA_VISIBLE_DEVICES=""`), which this model doesn't
  need; `setuptools<81` (Detectron2 imports `pkg_resources`); `MPLBACKEND=Agg`. SAM 3 and SAM 3D Body come from
  public mirrors (cubert-gmbh/sam3, gokayokyay/sam-3d-body, SHA256-checked) because Meta's repos are gated;
  switch to `facebook/*` once access is approved. Still upload-path / roadmap only, never live.

## Status 24 Oct 15:45

- **Andrii's footage** (`clips/andrii.mp4`, 2:10, 1080p60, solo, fixed camera, music audible at 86 bpm in 3/4):
  following now holds him in **1853/1948 frames** (95%). Soloists are now followed as the biggest clear person
  each frame; the clothing-colour check and the "moving" filter only apply to crowds (plain dark clothes in
  changing light broke the colour check; glass-door reflections are ignored by size). Render command:
  `python scripts/killtest.py clips/andrii720.mp4 --beats-per-bar 3` (720p30 copy for speed).
- **The team's hackathon project hit its spending cap** (429 RESOURCE_EXHAUSTED on key ...71sw, project
  `encode26lon-3459`, Tier 3, billing account ...7F15). All keys on that project share the cap, so switching keys
  there doesn't help. Likely cause: Deep Research glossary jobs (by far the most expensive calls). Anusha emailed
  Amit (DeepMind) ~15:50. Meanwhile use a key from a teammate's **own** temporary account, and **pause Deep
  Research** until there's fresh budget.
- Tip for filming: his feet leave the bottom of the frame when he comes close; start further back.

## Glossary in the narration (24 Oct, 16:15)

- All 18 waltz terms are now `vetted` (Andrii checked them; marked by Anusha at 16:10). **No beginner names yet**
  (`display_names.beginner`): per SPEC.md 5b, Anusha and Nastia confirm those (one enters, the other checks).
- Each phrase's movement is described in plain words and matched to the glossary with Atlas vector search
  (`db.match_terms(movement, style)`, same `gemini-embedding-2` / 3072 setup as the import). Only vetted terms are
  returned. `db.spoken_name(term, level)` picks the name: `professional` = canonical term, `beginner` = confirmed
  beginner name or nothing (plain description).
- Kill test / demo render: `--style waltz --terms professional` (or `beginner`, the SPEC default, which speaks no
  names until beginner names exist).
- Timing fix: 2-bar phrases (`--bars-per-phrase 2`, a line every ~4 s), the writer favours the last few seconds,
  and lines go in the earliest acceptable gap (`map_song(..., earliest=True)`). The checker's "floor" rule now only
  fires on going down ("to/on the floor", floor work, kneel...), not "across the floor".

## SAM for crowded clips: what to try (24 Oct, 16:45, for Nastia's Claude)

Goal: follow one named dancer/couple through crowded, handheld competition footage (the upload path, not the
live demo, which is a solo dancer YOLO already tracks in 95% of frames). **Timebox: one hour, then switch to the
YOLO benchmark and keypoint filtering.**

- **SAM 3 is unlikely to fit the 4070 laptop (8 GB).** Third-party install guides put it at ~10–12 GB for images and
  ~18–25 GB for short video. Its checkpoints are **gated on Hugging Face** (request access at
  huggingface.co/facebook/sam3, then `hf auth login` with a read token), and Meta recommends **WSL (Ubuntu)** on
  Windows rather than native builds.
- **Recommended instead: Robotics-ER + SAM 2.1 tiny.** `gemini-robotics-er-2-preview` turns words ("the girl in
  the red dress") into a box on one frame (tested, works); SAM 2.1 tiny (~40M parameters, fits easily in 8 GB)
  tracks that box through the video. Ultralytics (already a dependency) ships SAM 2 models; check its video
  predictor API before writing much code. Output should replace `track_focus`'s per-frame person boxes, then pose
  runs inside the tracked mask's box as now.
- Colab is the fallback for SAM 3 (free T4 for images; A100/L4 for video costs money, Anusha's call).

## Richer narration (24 Oct, 17:45)

Feedback from Anusha: lines sounded like a vision model listing what it sees ("hand pointed up, stepping"), not a
dance describer; facing was missing; turn directions were sometimes wrong; box steps weren't named.

- **Footwork per beat** (`footwork` in `scripts/killtest.py`): fb / side / close / hold from the feet, with body-height
  change counting as forward/back when facing the camera; "box step" = forward or back, side, close (twice, or half
  plus another forward/back step in a 2-bar phrase). Thresholds tuned on Andrii's clip only.
- **Turn direction** (`turn_direction`): the face leads the shoulders into a turn; `rotation` is the dancer's own side.
  Writer says "turns to his right" for rotation and "moves to the left" (audience view) for travel; the checker rejects
  a turn side that doesn't match the measured rotation.
- **Facing** (`facing_of`): front / back / side-on left or right from shoulder order, face visibility and nose
  direction; changes become events ("now with back to the audience").
- **Argon director wired in** (`--director`): on Andrii's clip it identified solo ballroom shadow work (waltz / slow
  foxtrot, 0.9), five sections, and motifs, and recognised the raised arm as his **ballroom frame for an imaginary
  partner**. Each phrase gets notes (section, recurring motifs with first appearance, verified key moments).
- **Writer rewritten as an audio describer:** knowledgeable about the style, uses the director's notes, explains a term
  the first time, says when facing changes, never repeats (says what changed or stays silent), skips incidental
  gestures, varies openings. Up to 12 words (checker limit 14).
- Demo render: `python scripts/killtest.py clips/andrii720.mp4 --beats-per-bar 3 --bars-per-phrase 2 --style waltz
  --terms professional --director`

## Raw clips for the team (24 Oct, 18:00)

Unannotated test footage is in the **private** repo https://github.com/anushaisawesome/unseen-steps-clips (Nastia and
Andrii invited). Clone it and copy the files into `clips/` here. The 1080p60 `andrii.mp4` is a release asset (too big
for git). **Never put clips in this repo:** it's public, clip1–4 show other couples at a competition, and Mixkit's
licence doesn't allow redistributing the raw stock.

## Why narration was crude, and the fix being tested (24 Oct, 18:00)

Anusha's feedback: the ballet render named none of the moves (missed starting in fifth, the grand jeté); lines carry no
expression or emotion; "how is this better for a blind person than the music alone?"; groups (formations, unison, a
central soloist, breaking into pairs, travelling across the stage) aren't handled at all.

**Diagnosis:** the information flows the wrong way round.
1. The **writer barely sees the dance**: coarse 2D stick-figure numbers and three stills per phrase. That can't show
   turnout, fifth position, pointed feet, épaulement, jump height or emotion.
2. The **glossary gates instead of teaching**: only vetted terms may be spoken and only waltz exists, so "grand jeté"
   was effectively forbidden on ballet.
3. The **checker only knows ~6 words**, which pushes lines towards bland mechanics.
4. **Metronome timing**: a line per phrase whether or not anything happened, not at the moments that matter.
5. **Single-dancer design**: no idea of formations, unison, canon or soloists.

**Test: Argon as the describer** (`scripts/argon_script.py`, whole video + an expert-describer brief, thinking high):
- **Ballet clip (27 s to run):** "a ballerina stands in fifth position, feet neatly crossed" / "glides sideways in a
  glissade, then springs into a soubresaut" / "hopping open in an échappé" / "from a deep plié … soars in a split
  sissonne, arms crowned overhead" / "arches back in a lyrical cambré, gaze lifted serenely skyward".
- **Group competition piece** (public YouTube link given to Gemini directly, not downloaded; 69 s): 24 timed lines
  covering formations (wedge, V, split groups), unison vs canon, soloists, lifts, floorwork, travel and named street
  styles (tutting, waacking, krump-style chest hits, body waves), with dynamics ("fierce, grounded weight",
  "defiant swagger", "reach up yearningly"). Not yet verified by a dancer.
- Saved outputs: `data/experiments/*.json` (gitignored).

**Proposed architecture (awaiting Anusha's decision):** Argon writes the description; pose and music become the
fact-checker and the timekeeper. This matches how real dance audio description works: describers prepare a script
from rehearsal recordings and deliver it live in time with the performance.
- **Rehearsed live show:** Argon writes a timed script from the rehearsal video (a describer can edit it); live, pose +
  music track where we are, deliver each line on cue, and check the live dancer matches (direction, jumps).
- **Upload:** Argon describes the video directly (richest), pose checks claims and draws the skeleton.
- **Improvised live:** short clips to Gemini as they happen; lower ceiling.
- The glossary becomes context that teaches the vocabulary (and the beginner/professional names and translations),
  not a whitelist; the checker keeps vetoing contradicted claims (jump with no rise, wrong travel direction).

## Decided: Argon writes the script (24 Oct, evening)

Anusha approved the Argon-as-describer direction after hearing the test lines. **This replaces per-phrase Flash
writing as the main pipeline** (`--script` in `scripts/killtest.py`; the old path stays as the fallback).

- **`server/scriptwriter.py`:** Argon watches and listens to the whole video with the music map and the style's
  vetted glossary, and writes timed lines: `time`, `moment_start/end` (the movement described), `who`
  (solo/pair/group/subgroup), `kind` (description or callout), `pace` (calm 2.0, measured 2.5, brisk 3.0, rapid 3.6
  words/s) and `delivery` (a short tone note). It picks its own timing: fuller lines in quiet gaps, and in explosive
  sections rapid callouts on the hits (Anusha's example: "Hit above the head! To the side! Fold to the right!").
  Cached in `data/director/script-<hash>.json`.
- **Music map** (`server/music.py`) now also returns `energy` per bar (0 to 1) and `hits` (strongest accents).
- **Checking:** each line is checked against pose features for its moment window (solo/couple: `phrase_features`;
  group of 3+: `group_features`, which only measures headcount and whether anyone is on the floor; jumps, turns,
  travel are `None` = unchecked in groups). The checker skips claims whose measurement is `None`, knows ballet jump
  and turn names (jeté, sissonne, soubresaut, entrechat, fouetté, chaîné...), ignores "turnout" and "gaze lifted",
  and the word limit is per line from its time budget. Rejected lines go back to Argon once (`revise`), else silent.
  Group pieces draw every dancer's skeleton; kneeling/sitting dancers (set aside as "seated" for spectator
  filtering) are kept in `SEATED` for group checks.
- **Voice** (`server/speech.py`): Gemini TTS **doesn't support a system instruction**, and in-text directions are
  unreliable ("Say fast...:" gets read aloud; a `# DIRECTOR'S NOTES / # TRANSCRIPT` prompt mostly isn't, and worked
  for calm lines). So: the delivery note goes in the director's-notes format, each clip is transcribed with Flash and
  regenerated plainly if extra words were spoken, and **speed comes from ffmpeg `atempo`** (up to 1.35x) to fit the
  time before the next line. Lines never overlap: a late line shifts, or is dropped if > 2 s late (callouts > 0.6 s).
- **Where the glossary goes now:** (1) into Argon's prompt as the style's vocabulary with the listener's
  beginner/professional names, teaching rather than gating; (2) translation names for `localise.py`; (3) next: per-term
  `signature` rules in the checker, terms Argon uses that aren't in the glossary saved as `auto` drafts for review,
  and Atlas Vector Search to map Argon's wording to the canonical entry. Ballet etc. without a glossary use Argon's own
  knowledge.
- **Live demo implication (team decision needed):** a script needs a recording first. For the live demo, Andrii
  dances a set routine that matches a rehearsal recording to the same song (the script is written from it, and live
  pose keeps it in step), or live falls back to the per-phrase Flash path.
- Ballet result: "stands in fifth, feet crossed" / "bends in plié and springs straight up" / "pas de bourrée, she
  leaps again" / "a soaring sissonne, legs split wide in the air"; the checker caught "gliding left" (no travel
  measured) and Argon's revision dropped the direction.
- Competition test clip `clips/judas.mp4` (Anusha's own download, not in any repo): 20-dancer commercial piece.

### Pacing rules (Anusha, 24 Oct evening): the music is the star

Feedback on the first script render: "far too slow, dragging, over the music too much. It's not reading a speech, it's
tastefully providing commentary while the music remains the main reference. Lines stay in meter and don't become the
star of the show."
- Brief: most lines 3 to 8 words, inside one bar (a few take two); speech at most a third of the running time; in
  lyrical passages at most one line every two bars; no slow pace (paces: steady 2.8, brisk 3.2, rapid 3.8 words/s).
- **In meter:** `scriptwriter.in_meter` snaps every line start to a beat; `killtest.in_beats` gives each line the whole
  beats its words need at its pace (never past the next line, max 2 bars); a collision moves to the next free beat
  (within a beat for callouts, a bar otherwise) or is dropped.
- **Voice was the drag:** every Gemini voice measured ~1.7 words/s because each clip has ~0.25 s of silence at both ends
  and 0.25–0.4 s pauses at every comma. `speech._tighten` trims ends and shortens pauses (ffmpeg silenceremove, -35 dB
  rms); a 4.2 s clip became 2.9 s. Then `atempo` up to 1.35x to fit.
- Mix: music 0.85, narration 1.3 (was 0.6 / 1.8).
- Ballet went from 83% of the clip spoken to 44%, four lines: "Backlit in white, feet crossed in fifth." / "A soubresaut,
  springing with feet tight together." / "Grand jeté, leaping high in a split." / "She arches toward the light."
- Pose detection is cached per video in `data/killtest/cache/` (gitignored), so re-renders skip the slow part.
- **Hard speech cap** (`SPEECH_SHARE = 0.35` in `scripts/killtest.py`): Argon gives each line a `priority` (1 essential,
  2 helpful, 3 optional colour); if speech would exceed 35% of the piece, optional then helpful description lines are
  cut, most crowded first; callouts are never cut. Judas went from 51% to 36% (6 lines cut), Andrii 32% (1 cut).
- Checker: "roll" only counts as floor work when it isn't a head/shoulder/hip/chest/body roll.
- Known weak spot: when the checker strips a direction, Argon's revision can produce an odd phrase ("A natural return
  back to profile"); worth a describer pass over the script before a show.
- **Annotated demos (script mode):** `docs/media/ballet-script-demo.mp4` and `docs/media/andrii-script-demo.mp4` in this
  repo; the Judas group render is a release asset in the private clips repo (release `annotated-1`), because it's
  another crew's choreography and this repo is public.

## Tuning workflow (Anusha + Nastia, from Sat 19:00)

Anusha and Nastia each find clips, render them in script mode, watch, and write feedback; the feedback drives
changes to the describer. Steps in `feedback/README.md`.
- Every `--script` render writes `data/killtest/<clip>-script-review.md`: each line with its time, status (spoken, cut for
  space, no room, rejected by the checker), kind, pace, priority and the moment it describes, plus blank feedback
  fields and the brief version. Filled-in reviews go to `feedback/<clip>-<name>.md`.
- **For Claude reading feedback:** look for patterns across reviews before changing anything; most fixes belong in
  the BRIEF in `server/scriptwriter.py` (what to say, how long, how often), the checker (false rejections), or the
  pacing constants (`SPEECH_SHARE`, `RATE`, `in_beats`). Quote the feedback that motivated a change in the commit.
- **One person edits `server/scriptwriter.py` at a time** (pull first, say so in the team chat), so the two of you
  don't conflict. Changing the BRIEF changes its hash, so Argon writes a fresh script (the cache is keyed on it);
  pose is cached per clip, so a re-render takes minutes.
- Cost: each new script is one Argon call on the whole video with high thinking. Keep clips under ~3 minutes, and
  keep an eye on the key's spending.
- **Finding clips:** your own or teammates' footage, or free stock (Mixkit, Pexels). Never download from YouTube or
  Instagram (their terms forbid it); Gemini can read a public YouTube link directly (`scripts/argon_script.py`) for
  script-only tests. Raw clips stay out of this public repo.
- Aim for a spread: solo, couple and group; lyrical and explosive music; ballet, ballroom, contemporary, hip hop,
  commercial; fixed and handheld camera.

**Pipeline explainer for the team (24 Oct, 19:30):** https://claude.ai/artifact/1YMrgTFi7Dks4vueFZyiKP (diagram, each
stage, how checking works, pacing rules, what's built vs not, commands). Submission text: https://claude.ai/artifact/9wqknz9gKac4m97zJkZNNj.

### Ballet fixes (24 Oct, 19:45)

Anusha: "tracking is worse for the ballet, and where are the names of the steps?"; "sometimes the voice doesn't say what
the captions are saying".
- **Names first:** the short-line rule had squeezed step names out ("Glides left, springs up" instead of glissade). The
  brief now says lead with the step's name, every recognisable step gets its name, and the opening line (scene and
  starting position) and every named step are priority 1, so the speech cap never cuts them. Ballet now: "Fifth
  position, feet neatly crossed." / "Soubresaut, springing with legs tight." / "Glissade into a split sissonne." /
  "Port de bras, arching back."
- **Tracking:** it wasn't worse; the new render drew skeletons in backlit frames the old one left blank, with wrong legs.
  Now `--model` works without `--seed` too (pose cache keyed per model), and only keypoints with confidence > 0.5 are
  drawn (`DRAW_CONF`). For uploads use `--model yolo11x-pose.pt`: on the ballet it follows her cambré properly and draws
  nothing mid-leap instead of wrong legs (3 min for 23 s on the Mac).
- **Voice vs caption:** `speech._faithful` now asks Gemini Flash whether the clip says exactly the caption (nothing added,
  dropped or swapped; dance-term pronunciation allowed) and re-records up to three takes (tone note twice, then plain),
  printing what was heard on each mismatch and a WARNING if all three fail.

### Two-pass Argon (24 Oct, ~20:15)

Anusha's Judas feedback (`feedback/judas-anusha.md`): canons missing, tutting called "miming crowns", a whole floorwork
section silent, some motion language inaccurate.
- Script mode now calls `director.performance_map` first. Its sections now carry `formation`, `group` (unison, canon and
  its direction, soloists, pairs) and `techniques` [{name, evidence}]; the map cache is keyed on the prompt and schema.
  `scriptwriter.structure_notes` feeds the map into the script prompt.
- Brief: every section gets a line and its first line is priority 1; canons and group-structure changes are priority 1;
  name the technique, not a mime ("tutting, hands framing a crown").
- Judas result: 7 sections mapped (canon at 69–90 s, floorwork at 90–122 s, tutting at 122–144 s); script now has "Canon, a
  wave left to right, dropping to sit!", "Tight central block, tutting, geometric hand frames.", "Floorwork in the
  center, seated leg extensions left.", "Kneeling waacking, fast overhead arm circles." Speech 41% (priority-1 lines
  aren't cut, so the cap can be exceeded). Weak spot: the 128–144 s chorus got one line, no callouts.
- The caption check caught the voice reading "Director's notes: Driving, bold", saying "whacking" for waacking and "one
  leg hype" for "one leg high"; all re-recorded until they matched.

## YouTube demos (24 Oct, ~21:00)

`scripts/youtube_demo.py` makes narration demos for public YouTube videos **without downloading them**: Gemini reads the
link directly (`director.video_part`, with `start`/`end` clipping through `VideoMetadata`), Argon maps then scripts the
piece (no music map: it keeps time by ear; no pose: lines are unchecked, and the page says so), each line is voiced,
checked against its caption and fitted, the 35% cap applies, and `web/youtube-demo/index.html` plays the narration over
YouTube's own embedded player (captions in a live region, music ducked to 70%, current section, clickable script with cut
lines struck through). Serve with `cd web/youtube-demo && python -m http.server 8765`.
- 16 videos in `VIDEOS`: Anusha's 7 links (Paris Cavanagh x2, Ponyboy, Streetstar 2013 vogue femme battle/solos, Saumya
  Red Bull fusion) plus ballet, contemporary, waacking, tutting, Bharatanatyam, flamenco, amapiano, afrobeats, ballroom.
- Audio files are named by a hash of their text + tone (a stale file can't pair with a new caption) and reused if present.
- Gemini clients are created before the worker threads (lazily created clients raced: "client has been closed").
- Brief additions from Anusha's feedback (`feedback/youtube-demos-anusha.md`): fusion (name each influence and use its
  vocabulary); arm-driven styles (arms' path and dynamics; callouts on accents for sharpness); the piece's signature is
  priority 1; `SPEECH_CEILING` 0.40 (essential lines cut only past it).

### Taste, not hardcoding (24 Oct, ~21:30)

Anusha: "don't hardcode it, make the detection have more taste. I can see it because I have eyes, but don't make those who
can't see miss out on it... for all of them, don't miss out on key features of the choreo." So the style-specific lists in
the brief were removed and replaced with three general mechanisms:
- **Signature in the map:** `performance_map` returns `signature` [{quality, body, dynamics, times}]: the 2–4 things a
  sighted viewer notices and remembers about this choreography. The script must convey every one; such lines are
  priority 1. (Track 10: "sculptural overhead arm and wrist framing", "grounded, wide-stance upper-body isolations".)
- **A second describer** (`scriptwriter.review_script`, cached): Argon watches the video with the map and the script, asks
  what a blind listener would miss, and returns up to 10 replace/add/drop edits. Its notes show on the demo page.
- **A line budget up front** (`scriptwriter.room`): "this piece runs N s, room for about M lines" (35% of the length at
  ~3 s a line), for both the writer and the reviewer, so Argon chooses what to keep instead of the blunt cutter. The
  cutter stays as a safety net and never cuts the opening line. Over-long lines go back to Argon once (`revise`).

### Texture changes (24 Oct, ~22:00)

Anusha: Track 10 "loses the bit where the texture changes from sharp to fluid for the buildup at about 12 s... this kind of
thing needs to be picked up on for styles I can't comment on as well. It's important." Also: hits missed (the clap and
turn before the vocals), first line cut, nothing on the arm work, 10 s silent while a lot happens.
- Map: `dynamics` timeline [{start, end, texture, energy, music}], a new entry whenever the quality of movement changes,
  even mid-section. Every change is priority 1 in the script and checked by the reviewer.
- Pose (local renders, solo/couple): `killtest.measured_texture` measures jerk-for-speed at wrists and ankles, labels
  half-seconds clearly sharp / clearly fluid, and reports switches between runs of 3 s or more; passed to Argon as
  evidence. Quiet on Andrii's waltz and the ballet (correct for steady pieces); not yet tested on a clip with a real change.
- Budget in seconds, not lines (callouts ~1 s, descriptions ~3 s), so sharp passages can carry callouts; big accents
  (a hit, a clap, a turn into a new phrase) are called; no more than ~6 s of quiet while new movement happens; the cap
  never opens a gap over 8 s and never cuts the opening line.
- Terms must meet their definitions (plié and ballet positions need turnout); `turnout` measured from knees vs ankles when
  facing the camera; the checker rejects plié/positions when knees measure turned in.
- **Trimming with taste** (`scriptwriter.trim`): when speech runs over 35%, Argon is given the real line lengths and the
  allowed time and picks what to drop (keeping opening context, signature, texture changes, big accents, key shapes;
  never more than ~6 s of silence during new movement). If a gap over 8 s remains, the shortest dropped line inside it
  comes back. The blunt cutter is only a final safety net. Aquamarine (Anusha's reference, "70% there"): 10 of 17 lines
  kept at 38%, signature line kept, gaps ~6–7 s.
- **Pose rule:** at holds, hits and arrivals, give the shape (limbs, line of the body, level, gaze); the reviewer checks it.

## Reset: principles, 5 fps, no speech cap (24 Oct, ~22:45)

Anusha: "take my feedback generally... always find the root complaint"; "why is there so much silence and so many lines
cut they may as well not be there"; "it missed the canon on ponyboy, why is this degrading in quality".
**Root causes found:**
1. The ballet note ("drags, talks over the music") was a delivery problem (slow voice, long lines, placement), but it
   became a hard 35% speech cap plus cutting machinery (line budgets, priorities, cutter, trim, gap restoring). Every
   piece of it deleted lines Argon wrote while watching: long silences, good lines cut, Ponyboy's canon lost.
2. **Gemini watches video at 1 frame per second by default.** At that rate it can't see sharp vs fluid, hits or arm
   detail, and it guesses timings. Checked on Aquamarine 15–26 s at 5 fps: far richer, second-by-second detail.
3. The brief had grown a rule per note, and each change was only checked on one video.
**Changes:**
- `director.FPS = 5` for every Gemini video read (`video_part`), YouTube and uploaded files; caches keyed on it.
- The cap, budgets, priority cutting and trim are gone. Only collision handling remains (a line can't talk over the
  previous one). How much to say is Argon's call: dense passages carry more short lines and callouts, repeated or
  resting movement gets the music alone.
- The brief is rewritten as principles from all her feedback: the goal (a blind listener gets what a sighted viewer
  gets), signature, every texture/energy change as it happens, shapes at holds/hits/arrivals, group structure, big
  accents, sections, precise vocabulary (definitions, turnout, technique over mime, fusion), expression; short lines in
  the music, never continuous. The second describer only fixes and fills (up to 12 edits), no budget.
- **`scripts/regress.py`:** must-haves per video from `feedback/*.md` (Ponyboy canon; Track 10 arm work, sharpness,
  sharp-to-fluid at ~12 s, clap and turn before the vocals, rich end groove, opening context; Aquamarine texture and
  poses; Judas canon, tutting, floorwork; ballet fifth position and step names), judged by Gemini Flash from the
  timed lines, plus longest silence (> 8 s flagged) and longest line (> 10 words). Run after every change.
  Baseline before the reset: 9/14. The judge is lenient on "arm work" (passed Track 10 when Anusha said it was missing).

## Live narration: `scripts/live.py` (24 Oct, ~23:30) — improvised, nothing rehearsed

Anusha: "don't rehearse it, that's the same as hardcoding. We want to show how Gemini can think on its feet."
- The program plays the song itself (`sounddevice`, so it knows exactly where it is in the music; works on Windows) and
  watches the camera. YOLO-pose follows the biggest, clearest person every frame; skeleton and captions on screen.
- Half a second before each 2-bar phrase ends, Gemini 3.8 Flash gets the last 4 s as frames (2 a second, with song
  times), the pose features for the phrase, what's been said, Argon's running notes and the style's vetted glossary, and
  writes one line or chooses silence. The checker vets it against the live pose; Gemini TTS voices it; the music dips
  while it plays. Lines more than 8 s stale are dropped.
- Gemini 4 Argon watches in the background: every 20 s it updates notes (style, the dancer's signature, motifs, what just
  changed) from the last 20 s of frames; the live writer uses them.
- Test on Andrii's clip (70 s): 12 lines, waltz terms used ("closed change", "reverse turn", "box step"), the checker
  caught a wrong direction, ~5 s from phrase end to a spoken line (~2.5 s writing, ~2.5 s voice).
- Run: `python scripts/live.py --song <music file> --camera 0 --beats-per-bar 3 --style waltz --model yolo11m-pose.pt`
  (`--record out.mp4` saves the session with music and narration; `--camera <video file>` stands in for a camera;
  `--mute` keeps time silently for tests). Needs `pip install sounddevice` and ffmpeg on PATH. Press q to stop.
- Known: Argon without the style hint read Andrii's waltz frame as "mime-like, marionette arms"; pass `--style`.

### Live on the Gemini Live API; zoom-in; per-line visual check (25 Oct, ~00:30)

- **Live latency 5 s -> 0.9 s.** Measured: Flash writer 2.8–4 s (can't think less; frame count barely matters), Flash TTS
  2.45 s whole clip. The Live API (`gemini-3.8-live`, audio out only) watches streamed frames and speaks: first sound
  0.5–1.0 s after each "Now" prompt. `scripts/live.py` now uses one Live session for the whole performance (frames at
  2 fps, a prompt at each phrase end with the pose measurements, director notes and the checker's feedback; audio
  streamed into the mixer; `context_window_compression` and auto-reconnect). The checker can't veto a line already
  being spoken, so it flags it on screen and tells Gemini in the next prompt to put it right. Test on Andrii's clip:
  13 lines in 60 s, median 0.88 s to first sound. `--engine flash` keeps the old write-then-speak path.
- Anusha on Track 10 (again): "absolutely nothing on the armwork". Traced: Argon's first script had 5 arm lines; the
  density edit deleted them as repetition. Root: a piece's signature is continuous, so trimming reads it as redundant.
  Fix: the reviewer merges rather than drops the signature, and `scriptwriter.keep_signature` compares the edit with the
  original per signature quality and restores lines it lost (Track 10 now: arm detail in 5 of 10 lines).
- Saumya: Bharatanatyam posing in the second song never named, early waacking lost, "waacking rapidly" over still arms.
  Leiomy: hand performance at the start, arms into a freeze, constant head/hair whips all missing. Root: one pass over a
  3-minute piece skims detail, and nothing checked a YouTube line against its moment. Fixes:
  `director.zoom` (each section re-watched at 8 fps, second by second: techniques by style, arms/hands/head/hair/face,
  exact texture changes, shapes, canons, accents) feeds the script; `scriptwriter.verify_lines` checks every line against
  its moment at 10 fps (right movement, time, technique, speed) and corrects or drops it. Head, hair and face added to
  the body parts Argon attends to.

## Website: `web/` on Vercel (24 Oct, late; Nastia)

Now live at https://unseen-steps-studio.vercel.app (Vercel project `unseen-steps-studio`, Hobby scope `anushaisawesomes-projects`; Nastia's first deploy was `unseen-steps` on `nxstiaa`). Static pages plus two Python
functions; no build step. WCAG 2.2 AA aimed for (Lighthouse accessibility 100 on both pages); Atkinson Hyperlegible type.
- **Home (`index.html`, `app.js`):** the ballet solo with Unseen Steps' narration from a recorded `killtest.py --script`
  run (2D); music and narration as separate tracks with their own volumes, resizable captions, transcript, WebVTT
  download, and the reveal (skeleton video, bar/beat/phrase counter, spoken and rejected lines). Rebuild it from a new
  run with `python scripts/web_demo_media.py clips/ballet.mp4 data/killtest/ballet-script.json`.
- **Live venue (`listen.html`, `live.js`, `pose.js`, `features.js`):** the website version of `scripts/live.py`. YOLO11n-pose
  runs in the browser (`web/models/yolo11n-pose.onnx`, ONNX Runtime Web, WebGPU else WASM); `features.js` ports
  `phrase_features` (thresholds in seconds; leg and arm events only from joints YOLO can see). Every ~1.5 s, one request
  at a time, the last 4 s go to `api/describe.py` as 2 frames a second plus measurements, what's been said and Argon's
  notes; it writes with `live.py`'s LIVE_BRIEF on `gemini-3.5-flash-lite` (~1.5 s with frames; 3.8 Flash took ~5.4 s),
  one `checker.py` pass. Lines about movement more than 3 s old are skipped, never spoken late; only the newest waits
  while a line is spoken. `api/notes.py` runs Argon's NOTES_BRIEF on the last 20 s in the background. Device voice by
  default; the Gemini voice uses `speech._synthesise` only (`speak()` needs ffmpeg, which Vercel doesn't have).
- **The functions can't import `server/` or `scripts/`:** `python scripts/web_sync_server.py` copies the server modules and
  `live.py`'s briefs into `web/api/_unseen/`. Run it before every deploy; never edit the copies.
- **Deploy (from main now, not the site-final worktree):** copy the `.vercel` link into `web/` once (gitignored), run `python scripts/web_sync_server.py`, then `cd web && npx vercel@63.1.2 deploy --prod --yes`. `web/media/ballet.mp4` is gitignored (Mixkit raw stock) but must be on disk for deploys; get it from the clips repo. `GEMINI_API_KEY` is a Vercel environment variable; there is no
  access code, so anyone with the link spends on that key: keep the AI Studio spending cap.

### Richness: a dancer's eye, not more rules (24 Oct, ~23:30)

Anusha (after hours of feedback): "is it gonna do anything richer than 'she spins and taps her hip'... this is not
what I see"; "jumps and extensions mean something but apparently not in this AD"; Leiomy: hair and hands now caught,
the freeze still missed; YouTube ballet: tambourine called a fan, lines feel late.
**Strip-back experiment** (ballet 56–80 s, Argon at 8 fps): the pipeline said "Taps her hip" / "Double spin, fourth
pause, quadruple spin!"; a bare "expert ballet describer" prompt was already richer; adding a short description of a
dancer's eye gave "In the Esmeralda variation, she flicks her right foot up behind to tap her tambourine", "Dropping
into a lunging fourth, she suspends the pause, tambourine held out like a dare", "Over the low drumroll, she spins
four slow, centered turns on one point, opening wide on the crescendo". **Conclusion: the rule pile (word limits,
density targets, body-part checklists) made Argon report *what happened*; richness comes from asking for what a dancer
sees: the work and character, the quality and intention (what a jump or an extension expresses), the detail that
makes it impressive, how it plays with the music.** The writer and reviewer briefs were rewritten around that, with only
pacing (one line per musical phrase plus brief callouts; 5–12 words; one idea per line) and accuracy kept as rules.
Also: one idea per line (lines strung with commas/semicolons were "word salad"); no knock-on shifting (lines that
can't start within ~0.5 s are left out; pushing them made Leiomy drift late); the signature guard only restores a
quality that vanished completely (max 2 lines).

### Final shape of the describer (25 Oct, ~00:20)

- **Window-by-window writing is the default** (`scriptwriter.write_script_windowed`): Argon writes each stretch of up to
  20 s (the map's sections, split) at 8 fps with the whole piece's map for context, about one line every 5–8 s plus
  callouts on standout hits. Writing a 3-minute piece in one pass drifted in timing (the line check corrected 15 of the
  ballet's lines, mostly right movement at the wrong moment) and went generic; short windows gave "Waiting in the wings
  for La Esmeralda", "each elastic kick suspends on the beat". `--whole` keeps the one-pass writer.
- **Final cut with the video** (`scriptwriter.select_lines`): after voicing, Argon watches the video with the voiced
  lines and their real lengths and chooses which to keep for about a third of the piece (signature spread across it,
  texture changes, accents, how dancers relate; no rewriting; no silence over ~8 s during new movement). A gap over 10 s
  gets one line back as a safety net. Earlier cuts failed because they were blind (a fixed percentage, or text only).
- Style naming: an influence is named only when several distinct cues support it (the "weigh traditions worldwide" rule
  had tipped Track 10 into "Chinese classical / Dai dance"); styles with their own framework of elements (vogue femme,
  a ballet variation's sections, a flamenco palo) are described in those terms.
- Order: map + section zoom-ins -> windowed script -> second describer -> signature guard -> per-line visual check ->
  voice (line only, checked against the caption) -> final cut -> no-collision placement.

### Moments first, and the pitch plan (25 Oct, ~00:45)

Anusha's gripes, grouped (from the whole night): doesn't see like a dancer; misses what matters (arm work, sharpness,
texture changes, canons, accents such as Track 10's clap and turn before the vocals, grooves, Leiomy's hands/freeze/hair,
legs and feet, poses); wrong or late lines; delivery swings between wall-to-wall and 3 lines; my process (patching per
video, restarting, no finished videos). Root causes: Argon barely watched (1 fps, one pass); write-then-rescue with six
reshuffling passes; "don't drag" turned into fixed percentages; no stable check.
**Fix being tested (`youtube_demo.py --keymoments`, page `?key`):** the map's key moments (group-structure changes,
texture/energy changes, signature, striking moments incl. musical accents) are the backbone: each gets its own line,
written with the dancer's eye; other lines only where the music has room; no rewrite review and no final cut; the
per-line visual check and caption check stay. Reference videos: Track 10, Aquamarine, Esmeralda ballet. Freeze at 04:00.
Pitch and submission plan for the team: https://claude.ai/artifact/WUVqqiV2qvKaZtZgQwgEep (timeline, judging criteria
mapped to evidence, 3-minute video shot list, stage pitch with the eyes-closed hook, submission field updates, owners,
backups). Judging: innovation, technical execution, impact, usability; top 10 pitch at 15:00 and the audience votes.

## Framing and show notes (25 Oct, ~02:40)

**Framing (Anusha):** the technology is for small studios to use for their own shows, which don't usually have access
to rich audio description that captures the meaning of the dance; the users are the blind and partially sighted people
in their audience. Studios upload the rehearsal video; show notes are written from its audio and video so timing,
narration and richness are right, down to the style of dance, and can be tweaked. Live, YOLO pose runs on a live camera,
Gemini has the show notes and the context of the song and performance, and narrates in real time, taking into account
the dancer's live variation from rehearsal, in the gaps in the song it already identified.
- `server/show_notes.prepare` (map + key moments + notes text). `scripts/prepare_show.py --name ... --rehearsal ...
  --song ...` stores a show in MongoDB Atlas (`shows`: name, studio, style, song, bpm, gaps, plan, key_moments,
  show_notes). `scripts/live.py --show "<name>"` loads it from Atlas (or `--rehearsal <video>` prepares it on the spot):
  the Live session starts with the notes, prompts happen in the song's gaps (clean spaces), and each prompt says what
  rehearsal had around then and asks for what the dancer actually does now. Test: median 0.80 s to first sound.
- Live corrections no longer apologise ("My apologies, he performs a pivot to the left" before). Checker: "on his left"
  is a foot, not a direction.
- Scrutiny of the framing (answers in the pitch doc): groups (live tracking is solo today), "isn't it playback?" (Andrii
  deliberately varies from rehearsal in the demo), trust (checked when notes are made; live corrections come after),
  no notes editor yet (next), no blind user test yet (Gerard's dancers next), who pays (families at studio shows).

### Live wording: name the step, with grace (25 Oct, ~04:00; Andrii + Anusha)

Andrii's live test on Windows (`clips/live_session*.json`, local) said "closing the feet" / "bringing the feet together"
on every box-step phrase, and flat "stands still / frozen" lines. Cause: the `footwork` measurement sent to Live read
"half a box step (forward or back, side, close)", so the model echoed "close" each bar.
- **Decided:** live lines name the figure (box step, closed change, natural turn, reverse turn) every time it is danced
  and again when it returns; grace is in the wording ("waiting for the right moment", "letting the music settle"
  instead of "stands still"). A purely evocative line without the name is allowed only occasionally, not banned.
- Live gets `footwork` as just the figure name ("box step"), every phrase. A first attempt that sent it only once per
  section made the model drop the names entirely ("gliding smoothly", "elegant waltz rhythm"), so don't de-dup it.
- The Live model may stay silent when nothing new happened. Its transcription then reads `<no speech>{pause}`;
  `live.spoken_text` strips such labels so a silent turn isn't captioned, checked or logged.
- Also: the live window opens resizable at 1280x720 (it opened at full camera resolution on Windows).

### Video sources, rehearsal analysis and live tracking (25 Oct, ~01:00)

- **Keep the full video with its soundtrack as the canonical input.** An MP3 is enough for beat/phrase mapping but not
  for understanding the dance, because Gemini needs movement, staging and the relationship between movement and music.
  `server/music.py` already accepts an audio or video file and uses ffmpeg to extract the soundtrack internally.
- **Public YouTube:** Gemini can analyze the public YouTube URL directly, which is what `scripts/youtube_demo.py` does.
  That path avoids downloading but has no YOLO measurements. When post-tracking, local rendering or pose verification is
  required, download a permitted/public clip as MP4 with audio (for example with `yt-dlp`) and process that local file.
  Do not download material the team does not own or have permission to use.
- **Google Drive or another private source:** download the original MP4 through the Drive API, an authenticated download,
  or the app's normal upload flow, then upload the resulting file through Gemini's File API. A Drive sharing-page URL is
  not treated as a reliable direct video URI.
- **Recorded upload/rehearsal path:** Gemini/Argon analyzes the whole video plus audio for style, structure, meaning and
  key moments; YOLO pose runs afterwards on the same file for target tracking and measurable verification. Merge both
  outputs by timestamp.
- **Live path:** YOLO pose remains the fast frame-by-frame tracker. Gemini Live receives a lower-rate view plus YOLO
  measurements for semantic narration. YOLO alone tracks bodies but cannot infer the dance's meaning or relationship to
  the music.

### Live shares the tuned taste; show notes carry the rehearsal script (25 Oct, ~05:45)

Andrii saw live narration swing between technical terms and crude mechanics ("he waits", "puts his feet together").
Root cause: live used its own thin brief (a hardcoded waltz step list, stillness example phrases that leaked into the
output, 3 to 8 words), never read `feedback/`, and was handed raw pose numbers to narrate.
- `scriptwriter.DANCERS_EYE` is the writer's dancer's-eye brief (the writer's `BRIEF` = it + the pacing rules,
  byte-identical, so caches hold). `live.live_system()` = `DANCERS_EYE` + `dancer_feedback()` + `LIVE_RULES` (one line
  per "Now", about 4 to 10 words, may stay silent, name a step only when it clearly is one, never apologise). Tuning the
  writer or adding feedback now tunes live too. `LIVE_BRIEF` (the `--engine flash` fallback and the website) lost the
  waltz list and example phrases too.
- Pose measurements in each prompt are labelled a check only: don't contradict them, don't narrate them.
- `show_notes.prepare` also writes the rehearsal script with the tuned pipeline (windowed writer + per-line check, not
  voiced); `prepare_show.py` stores it in the Atlas show as `script`. Each live prompt quotes the rehearsal line(s) near
  that moment as the quality of language to match, while describing what the dancer actually does tonight. Shows
  without a script still work.
- Test on Andrii's clip (70 s, the camera being the rehearsal video itself): before, 12 lines such as "He waits, holding
  the ballroom frame steady." / "Stepping back, side, and closing." (x2); after, 8 lines such as "Dancer in headphones
  walks in, rolling his shoulders." / "Stepping back, side, together in a waltz box." / "Pivoting left into a quarter
  turn to face front." Median first sound 0.80 s -> 1.02 s (the longer system instruction). Some lines repeat the
  rehearsal wording when the movement is the same, by design.
- **After `git pull`, re-run `prepare_show.py` for any show prepared before this** (Demo: Andrii, waltz is done).

## DeepMind track: where we stand (25 Oct, morning; Andrii's Claude)

Pathway 2 (real-world video, live voice) fits. Judging: live demo 50%, problem and usefulness 25%, needed Argon 15%,
pitch clarity 10%.

| Criterion | Where we are | Rough score |
| --- | --- | --- |
| Working live demo (50%) | Andrii dances live, unscripted; voice ~0.8–1 s after each prompt (`live.py`, 3.8 Live). Real verification loops: pose checker vetoes contradicted lines, per-line visual check, caption check on the voice, live corrections on the next line. Argon builds the performance map and show notes from the rehearsal, plus notes every 20 s live. | Strong |
| Problem and usefulness (25%) | Small studios without audio description; blind and partially sighted audience members. **Gap: no named user, no blind-user test yet.** | Medium |
| Needed Argon (15%) | Argon watches the whole rehearsal with its music at 5–8 fps, zooms into sections, writes and checks the script (thinking high). **Weak: live speech is 3.8 Live, not Argon** ("isn't this just Gemini Live?"); people stay in control via `scripts/edit_show.py` (studio edits the Atlas show notes). | Medium–strong |
| Pitch clarity (10%) | Eyes-closed hook, live product, no slides. Depends on rehearsal. | Depends on rehearsal |

**To raise the score, cheapest first:**
1. **Name a person:** Gerard Canal (KCL) and the blind dancers he works with; a quote from one of them if possible.
2. **Show a verification loop live:** a checker flag on screen, plus one sentence saying what it caught.
3. **Answer "why Argon?":** "Argon is the choreographer's eye: it watches the whole rehearsal with its music in one context, finds
   sections, motifs and texture changes, and writes the show notes. Live is the voice that delivers them in time." Show the
   map / show notes on screen for a few seconds.
4. **Human control:** say a studio or describer edits the Atlas show notes before the show (`scripts/edit_show.py`, built).

**Don't claim:** Robotics-ER, Lyria, Antigravity (none are in the code; Robotics-ER was one manual test). The only
`background=True` call is the Deep Research glossary job, not Argon.
**Main risk:** live failure on stage (camera, audio routing, WiFi). Backup: `clips_public/live_session6.mp4` (recorded live session).

## The Real World track: where we stand (25 Oct, ~08:00)

Judging: real-world usefulness (a clear user, a problem outside the hackathon); how well it reads the world (accuracy,
sensible handling of messy inputs, gaps in the data); technical execution (end to end, AI models with real data);
responsibility (privacy of faces and locations, honesty about uncertainty). Submission: working demo, repo with README
and setup, a 2 to 4 minute video on real inputs, a note on models and data sources (now in README.md).

| Criterion | Evidence we have | Gap / what to show |
| --- | --- | --- |
| Usefulness | Studios' own shows; blind and partially sighted audience; Gerard's blind ballroom dancers; open-sourcing for studios | No blind-user test yet: say it's next, don't imply it happened |
| Reads the world | Pose checker live; per-line visual check; caption check on every clip; 0.3/0.5 keypoint confidence; checks skipped when unmeasurable; terms only when fully visible; live names only the routine's figures (SPEC 15a) | Show a checker catch on screen in the video |
| Technical execution | Live camera + real music map + Atlas glossary and shows + 17 real performances | Fine |
| Responsibility | Live frames not stored unless recording is chosen; narration in each listener's earphones; no other people's clips in the repo; studio edits notes (`scripts/edit_show.py`) | Everything outside the dancers being described is blurred in rendered videos (`killtest.py`, commit d20f873; face detection alone missed distant spectators) |

Changes made for it: README rewritten (problem, how it works, honesty and privacy, models and data sources, setup and
the show-night commands); `scripts/edit_show.py` (studios edit show notes in Atlas); live figure names limited to the
routine's own (SPEC 15a); checker false flags from SPEC 15c fixed.


## Atlas Search for songs (25 Oct, ~09:00)

`db.find_song(name)` runs `$search` (index `song_name`, fuzzy, maxEdits 2) on `songs.name`; `db.save_song` stores a
song's music map whenever `prepare_show.py` or `live.py` maps a file. Both scripts accept `--song "<name>"` as well as a
file path: a name is looked up in Atlas and its stored map and file are used. Andrii's rehearsal soundtrack is stored as
"Andrii's waltz (rehearsal soundtrack)". Atlas features in use: Vector Search (glossary) and Atlas Search (songs).
**Hybrid Search (built 25 Oct, ~09:30):** Anusha had the sample dataset's `sample_mflix.movies` `default` search index
deleted to free the third slot. `term_text` (Atlas Search on terms: term, aliases, description; style and status as
tokens) is READY. `db.match_terms_hybrid(text, style)` runs `$vectorSearch` and `$search` and fuses them by reciprocal
rank fusion in Python (1/(60+rank)); MongoDB 8.0 has no `$rankFusion`. Vetted terms only unless include_drafts. Used where
`killtest.py` offers glossary terms. Test: "rotates to the right as a couple, a natural turn" -> natural turn, natural
spin turn, turning lock; "steps forward, side, then closes the feet together" -> closed change first. Atlas features in
use: Vector Search, Atlas Search, Hybrid Search. The cluster's 3 search-index slots are now all ours.

## Licensing clean-up (25 Oct, after submission)

The waltz song (`clips_public/with_you_im_born_again_slow_waltz.wav`) and the raw Mixkit ballet clip (`web/media/ballet.mp4`)
are no longer tracked here: neither is ours to redistribute. **After `git pull` they disappear from your disk**; get them from
the private clips repo (`music/with_you_im_born_again_slow_waltz.wav`, `ballet.mp4`) and put them back at the same paths
(both are gitignored now). `video/cut4.py`, `live.py --song <file>` and website deploys still read them from those paths.
Git history still contains them; rewriting history is the team's call.

## Final demo video (25 Oct, ~11:35)

`video/cut4.py` builds it (2:59) from the 15-part script in `video/SCRIPT.md`; the render is in the private clips repo
`submission/`. Ballroom shots use the stretches of `waltz-annotated.mp4` where the tracked couple stays in frame (13-27 s,
74-78 s). Captions sit top-left, labels top-right with a clear gap; the venue screen-reader test (10.5-21 s: labelled
controls, Start listening, the first line) sits above the bottom caption. Submission files: the four PDFs, the architecture
PNG, the screen-reader test video and its announcements log.

## Finding a show by part of its name (25 Oct, ~10:00; Andrii's Claude)

A studio's recital is several shows (one per piece, each with its own song), so `live.py --show` and `edit_show.py` now
take part of the name: `db.find_show(query)` returns an exact name (any case) first, else the one show whose name, studio,
song or style contains every typed word at the start of a word ("andrii waltz", "year 3", "andri"). If several match
(two pieces to the same song), it stops and lists them rather than guess; none, it says so. Test:
`python server/db.py show "andrii waltz"`. **A plain MongoDB query, not Atlas Search** (no typo tolerance): the free
cluster's three search indexes are taken (`vector_index`, `term_text` for Hybrid Search, `song_name`), so don't claim it
as Atlas Search.

**Website fixes for Anusha (25 Oct, ~10:30, from Andrii):** consistent header/nav names across pages, redesign of the
"18 styles" page, green/red/pink shadows on the main page. Details in `SPEC.md` 15, "Immediate website fixes". Not implemented yet.

**ANUSHA: please make a slide / video card on tracking safeguards (25 Oct, ~11:00, from Andrii).** The six layers that
keep bad body tracking out of the narration (pose confidence, per-phrase coverage, unmeasurable = unchecked, crowded
footage goes silent, Gemini sees the frames too, people can see the skeleton) are in `docs/tracking-safeguards.md`, with
a one-line version for the pitch. Covers "how well it reads the world" (Real World) and the verification loop (DeepMind).

## Result: Google DeepMind Special Prize for Open Innovation (25 Oct, finale)

Unseen Steps wasn't among the top 10 finalists who pitched on stage (SceneBar, FlowArc, Second Sig, Axolotl,
MonsoonWatch, L Plate, deRoute, mosa, Dwelld, Anchorcare), but **Google DeepMind created a Special Prize for Open
Innovation for it: $2,000 in Google Cloud credits.** Their slide: *"Real-time audio description of choreography for
blind dance audiences, combining Gemini 4 Argon video understanding with sub-second Live voice synthesis."*
- The open-source, tool-for-studios framing (rather than a startup pitch) is what the prize recognised; keep it.
- README and both website footers mention the prize. The website needs a redeploy to show it (see "Website").
- Credits: who redeems the Google Cloud credits and what they fund (e.g. Argon show-note runs, a cloud GPU for the
  upload path) is still to be decided by the team.
- Next step stays the same: test with blind dancers and their audiences (Gerard's dancers first).

