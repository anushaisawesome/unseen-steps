# Unseen Steps: notes for Claude

Live audio description of dance for blind audiences, built at Encode London (23–25 Oct 2026) by
Anusha and Andrii. `SPEC.md` is the full specification; this file is the **current state and the
decisions made since**, so read this first. When a decision changes, update this file in the same
commit.

**Standing rule for every Claude on this repo:** anything Anusha and Andrii decide or discuss goes into this file in the same session, so the other person's Claude has it after `git pull`.

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
