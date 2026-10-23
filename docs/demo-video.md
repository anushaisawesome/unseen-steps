# Demo video spec

The submission video for Unseen Steps. One video serves every challenge we're entering.

## Requirements

| Challenge | Needs |
| --- | --- |
| Google DeepMind | 3-minute demo video; say which Gemini models we used and how |
| The Real World | 2 to 4 minutes, showing it working on real inputs |
| MongoDB | Show the app in action **and MongoDB in use** |
| All | Submitted on the Encode platform by **Sunday 25 October, 12:00** |

So: **exactly 3:00 or just under**, real footage, MongoDB visible on screen.

## Format

- 1920×1080 (720p minimum), 16:9, H.264 + AAC, 30 fps
- Captions burned into the picture (the narration is the product, so it must be readable with the sound off too)
- Under 100 MB so it uploads quickly on venue WiFi

## Storyboard

| Time | Shot | On screen | Audio |
| --- | --- | --- | --- |
| 0:00–0:15 | Black screen | "This is what a blind audience member hears." | Music with narration only, no picture |
| 0:15–0:35 | The person it's for | Gerard's dancer: voice note or quote, name if they agreed | Voice note, or narration reading the quote |
| 0:35–1:35 | **The product** | Andrii dancing live (backup: waltz clip) with skeletons, captions and voice (see Overlays) | Music plus narration in the clean spaces |
| 1:35–2:05 | How it works | Architecture diagram, then the checker rejecting a line and the rewrite that passed | Short voiceover |
| 2:05–2:30 | **MongoDB** | Atlas: vector search matching a phrase's features to dance terms, and the songs collection with clean spaces | Short voiceover |
| 2:30–2:50 | Gemini | Which model does what: Argon show memory, 3.8 Flash writer, Flash TTS / Live voice, Deep Research for vocabulary | Short voiceover |
| 2:50–3:00 | Close | Team, repo link, next step (training tool for blind dancers) | Music out |

## Overlays (drawn by `scripts/killtest.py`)

- **Skeletons:** the followed dancer in lilac `#FF78E6`, their partner in mint `#96EBAA`, other dancers on the floor in thin grey. Seated and standing spectators get no skeleton.
- **Caption:** the spoken line, centred near the bottom in Helvetica Neue on a dark rounded bar, from the moment it's spoken until half a second after it ends.
- **Title:** "Unseen Steps · live audio description", small, top left.
- **Checker note:** when a line was rejected before the one spoken, a red badge top right shows the rejected draft and why.

## Audio

- Music at 60% so the narration sits clearly on top; narration at 180%.
- Each line starts at its clean space (picked from the music map), never on the downbeat.
- Voice: Gemini `gemini-3.8-flash-tts`, voice "Kore". (The speech model returns a full WAV with a metadata block at the end; `server/speech.py` strips it, otherwise it plays as static.)

## How to render

```
# product footage with skeletons, captions and voice
python scripts/killtest.py clips/<clip>.mp4 --beats-per-bar 3 --seed <time>,<x>,<y>
# -> data/killtest/<clip>-annotated.mp4
```

`--seed` marks who to follow: a time in seconds and the dancer's position as fractions of the frame (e.g. `17,0.42,0.7`). Check it first with `python scripts/track_debug.py clips/<clip>.mp4 sheet.jpg --seed ...`.

## Footage to capture

- [ ] Andrii dancing live at the Saturday 20:00 rehearsal: fixed camera, whole body in frame, 1080p, his demo song
- [ ] Backup: the waltz clip, rendered with the red-dress couple followed
- [ ] Screen recording: a checker rejection and the rewrite (from the live page or the kill test output)
- [ ] Screen recording: MongoDB Atlas vector search and the songs collection
- [ ] Gerard's dancer: voice note or quote, with permission
- [ ] Optional: a judge or friend listening with eyes closed, then opening them

## Before submitting

- [ ] Length is 3:00 or less
- [ ] Captions readable on a phone
- [ ] MongoDB clearly on screen
- [ ] Every Gemini model named
- [ ] No static, narration audible over the music
- [ ] Uploaded before Sunday 12:00
