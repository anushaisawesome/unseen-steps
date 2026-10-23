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
