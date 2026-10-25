"""Live audio description: Gemini watches the dancer and describes on its feet. Nothing is scripted or rehearsed.

The program plays the song itself (so it always knows where it is in the music) and watches the camera:
- YOLO-pose follows the dancer every frame; the skeleton and captions are drawn on screen.
- At the end of every musical phrase (2 bars), Gemini Flash gets the last few seconds as frames, the pose
  measurements for that phrase, what's already been said and the director's running notes, and writes one short
  line (or chooses silence). The checker vets it against the live pose; the voice says it over the music, which dips.
- Gemini 4 Argon keeps watching in the background: every ~20 s it updates its notes on the style, this dancer's
  signature, recurring motifs and what just changed, so the live lines get smarter as the piece goes on.

Usage:
    python scripts/live.py --song music.mp3 [--camera 0] [--beats-per-bar 3] [--style waltz] [--record out.mp4]
    # test without a camera: a video file stands in for the camera (and its soundtrack for the song)
    python scripts/live.py --song clips/andrii720.mp4 --camera clips/andrii720.mp4 --beats-per-bar 3 --record live.mp4
Press q to stop.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import cv2
import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "server"))
from google.genai import types  # noqa: E402
from killtest import DEVICE, draw_skeleton, draw_text, load_pose, phrase_features, LEAD_COLOUR  # noqa: E402
from music import load_audio, map_song  # noqa: E402
from checker import check  # noqa: E402
from retry import with_retry  # noqa: E402
import director  # noqa: E402
import speech  # noqa: E402

RATE = 44100
LIVE_MODEL = "gemini-3.8-live"  # watches the frames and speaks: first sound ~0.5-0.8 s after each prompt
WRITER = "gemini-3.8-flash"     # fallback engine (--engine flash): writes, then TTS speaks; ~5 s
DIRECTOR = "gemini-4-argon"
CLIP_SECONDS = 4.0   # how much the writer sees for each line
CLIP_FPS = 2         # frames a second sent to the writer (more slows the reply)
NOTES_EVERY = 20.0   # seconds between the director's updates

LIVE_BRIEF = """You are an expert audio describer for dance, describing a live performance for blind and partially
sighted listeners as it happens. You see the last few seconds (frames, oldest first, with their times in the song)
and the pose measurements for that stretch. Say the one thing a blind listener most needs right now, the way a
sighted viewer would experience it: the step by its name if it has one (only if every part of the term's definition
is visible), the shape the body makes, the texture or dynamics (sharp or sustained, light or heavy), a change in
energy, or a striking accent. Never repeat what has already been said; if nothing new or important happened, return
null and let the music play.
Rules: 3 to 8 words (a callout on a hit, 2 to 5 words); present tense; directions as the audience sees them ("to the
left"); only what you can see. Return JSON {"line": "..." or null}."""

NOTES_BRIEF = """You are the director of a live audio description of a dance, watching it as it happens. Frames from
the last stretch are attached (oldest first, times in the song). Update your running notes for the live describer in
at most 5 short bullet points: the style; the signature of this dancer's movement (what a sighted viewer notices most:
where it lives in the body, its dynamics); recurring motifs and when they return; what just changed. Keep what is
still true from your previous notes. Plain text bullets only."""


LIVE_SYSTEM = """You are an expert live audio describer for dance, speaking to blind and partially sighted listeners
while they hear the music. You watch the camera frames as they arrive. Each time you are prompted with "Now", say ONE
short line (3 to 8 words; a callout on a hit, 2 to 5) about what the dancer just did that a sighted viewer would notice
most: the step by its name (only if every part of its definition is visible), the shape the body makes, the texture or
dynamics (sharp or sustained, light or heavy), or a change in energy. Directions as the audience sees them. Use the
measurements in the prompt: never claim a turn, jump, floor work or direction they don't support, and if you're told
a line was wrong, put it right in the next one by simply describing correctly: never apologise or mention the
mistake. Never repeat yourself: don't name the same step twice in a row, and
don't start lines the same way ("He performs", "He executes"); if the movement repeats, say something new about it
(its texture, the arms, the shape, the feeling) or just a few words. Speak briskly and warmly, like commentary inside
the music. Say only the line."""


class LiveEngine:
    """One Gemini Live session for the whole performance: frames stream in continuously; at each phrase end a short
    "Now" prompt (with the pose measurements, the checker's feedback and the director's notes) makes it speak, and
    its audio streams straight into the mixer."""

    def __init__(self, live):
        self.live, self.loop, self.queue, self.ready = live, None, None, threading.Event()
        self.busy, self.turn = False, None

    def start(self):
        threading.Thread(target=lambda: asyncio.run(self.main()), daemon=True).start()
        if not self.ready.wait(20):
            raise RuntimeError("couldn't connect to Gemini Live")

    def send(self, kind, payload):
        if self.loop:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, (kind, payload))

    async def main(self):
        self.loop, self.queue = asyncio.get_running_loop(), asyncio.Queue()
        system = LIVE_SYSTEM + (f"\nThe style is {self.live.args.style}." if self.live.args.style else "")
        if self.live.show_notes:
            system += ("\n\nShow notes, prepared from the studio's rehearsal video of this piece (the song and times "
                       "are the same tonight). Use them to know the style, the vocabulary, what makes this choreography "
                       "distinctive and what is coming, but describe what the dancer actually does now: if tonight "
                       "differs from rehearsal, say what you see.\n" + self.live.show_notes)
        if self.live.glossary:
            system += "\nVocabulary vetted by dancers (use a term only if what you see matches it):\n" + "\n".join(self.live.glossary)
        config = {"response_modalities": ["AUDIO"], "output_audio_transcription": {},
                  "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": "Kore"}}},
                  "context_window_compression": {"sliding_window": {}},  # keeps long performances going
                  "system_instruction": system}
        while True:  # reconnect if the session drops; the performance carries on
            try:
                async with director.client().aio.live.connect(model=LIVE_MODEL, config=config) as session:
                    self.ready.set()
                    receiver = asyncio.create_task(self.receive(session))
                    while True:
                        kind, payload = await self.queue.get()
                        if kind == "frame":
                            await session.send_realtime_input(video=types.Blob(data=payload, mime_type="image/jpeg"))
                        elif not self.busy:  # a line still being said means this phrase passes in silence
                            self.busy, self.turn = True, {**payload, "phrase_end": payload["end"],
                                                          "asked": time.perf_counter(), "words": "",
                                                          "at": None, "end": None, "pcm": bytearray()}
                            await session.send_client_content(
                                turns={"role": "user", "parts": [{"text": payload["prompt"]}]}, turn_complete=True)
                        if receiver.done():
                            receiver.result()
            except Exception as e:
                print(f"live session dropped ({type(e).__name__}: {str(e)[:80]}); reconnecting")
                self.busy = False
                await asyncio.sleep(1)

    async def receive(self, session):
        while True:
            async for m in session.receive():
                turn, content = self.turn, m.server_content
                if turn is None:
                    continue
                if m.data:
                    if turn["at"] is None:
                        turn["at"] = self.live.mixer.now() + 0.03
                        turn["latency"] = round(time.perf_counter() - turn["asked"], 2)
                    turn["end"] = self.live.mixer.push(m.data, 24000, turn["end"])
                    turn["pcm"] += m.data
                if content and content.output_transcription and content.output_transcription.text:
                    turn["words"] += content.output_transcription.text
                    self.live.caption = (turn["words"].strip(), turn["at"] or 0, (turn["end"] or 0) + 0.4)
                if content and content.turn_complete:
                    self.busy = False
                    self.live.spoken(turn)


class Mixer:
    """Plays the song and mixes narration over it, ducking the music while a line is spoken. The number of samples
    played is the clock everything else is timed against."""

    def __init__(self, song: np.ndarray, mute: bool = False):
        self.song, self.pos, self.voices, self.lock = song, 0, [], threading.Lock()
        self.mute, self.started = mute, None
        self.stream = None if mute else sd.OutputStream(samplerate=RATE, channels=2, dtype="float32", callback=self._fill)

    def start(self):
        self.started = time.perf_counter()
        if self.stream:
            self.stream.start()

    def stop(self):
        if self.stream:
            self.stream.stop()

    def _fill(self, out, frames, _time, _status):
        with self.lock:
            chunk = np.zeros((frames, 2), dtype=np.float32)
            part = self.song[self.pos:self.pos + frames]
            chunk[:len(part)] = part
            speaking = False
            for start, voice in self.voices:
                a, b = max(start, self.pos), min(start + len(voice), self.pos + frames)
                if a < b:
                    chunk[a - self.pos:b - self.pos] *= 0.7 if not speaking else 1.0  # music dips under the voice
                    chunk[a - self.pos:b - self.pos] += 1.3 * voice[a - start:b - start]
                    speaking = True
            self.voices = [(s, v) for s, v in self.voices if s + len(v) > self.pos]
            self.pos += frames
        out[:] = np.clip(chunk, -1, 1)

    def now(self) -> float:
        if self.mute:  # same clock, no sound (for tests)
            self.pos = int((time.perf_counter() - self.started) * RATE) if self.started else 0
        return self.pos / RATE

    def _busy_until(self) -> int:  # call with the lock held
        return max((s + len(v) for s, v in self.voices), default=0)

    def say(self, wav_path: Path) -> tuple[float, float]:
        """Queue a spoken line right after anything already being said; returns (start, seconds) in song time."""
        with wave.open(str(wav_path)) as f:
            sr, raw = f.getframerate(), f.readframes(f.getnframes())
        mono = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
        mono = np.interp(np.arange(0, len(mono), sr / RATE), np.arange(len(mono)), mono).astype(np.float32)
        voice = np.stack([mono, mono], axis=1)
        now = int(self.now() * RATE)
        with self.lock:
            self.voices = [(st, v) for st, v in self.voices if st + len(v) > now]
            start = max(now + int(0.05 * RATE), self._busy_until() + int(0.15 * RATE))
            self.voices.append((start, voice))
        return start / RATE, len(voice) / RATE


    def push(self, pcm16: bytes, sr: int, start_after: float | None) -> float:
        """Stream a chunk of spoken audio: it plays straight after the previous chunk of the same line (start_after,
        in song time), or now if this is the line's first chunk. Returns where the chunk ends, in song time."""
        mono = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768
        mono = np.interp(np.arange(0, len(mono), sr / RATE), np.arange(len(mono)), mono).astype(np.float32)
        now = int(self.now() * RATE)
        with self.lock:
            start = int(start_after * RATE) if start_after is not None else now + int(0.03 * RATE)
            start = max(start, now)
            self.voices.append((start, np.stack([mono, mono], axis=1)))
        return (start + len(mono)) / RATE


def decode(path: str) -> np.ndarray:
    """The song as float32 stereo at RATE (ffmpeg reads mp3, wav, mp4...)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(RATE), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def jpeg(frame, width=512) -> bytes:
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (width, int(h * width / w)))
    return cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()


class Live:
    def __init__(self, args):
        self.args = args
        self.song_map = map_song(load_audio(args.song), beats_per_bar=args.beats_per_bar, bars_per_phrase=2,
                                 speech_seconds=2.5, earliest=True)
        self.mixer = Mixer(decode(args.song), mute=args.mute)
        self.pose = load_pose(args.model)
        director.client(), speech.client()  # create the clients before the worker threads
        self.path, self.frames = {}, []      # song time -> [person]; (song time, jpeg) at CLIP_FPS
        self.said, self.notes, self.log = [], "", []
        self.caption, self.badge = None, None
        self.done_phrases, self.lock = set(), threading.Lock()
        self.last_notes = 0.0
        self.glossary = []
        if args.style:  # the dancers' vetted vocabulary for this style, if the glossary has it
            try:
                from db import db, spoken_name
                for term in db()["terms"].find({"style": args.style, "status": {"$in": ["vetted", "translated"]}}):
                    if name := spoken_name(term, args.terms):
                        self.glossary.append(f"{name}: {term['description']}")
            except Exception as e:
                print(f"glossary unavailable ({type(e).__name__}); Gemini uses its own vocabulary")
        print(f"glossary: {len(self.glossary)} terms")
        self.feedback = ""   # the checker's verdict on the last line, for the next prompt
        self.plan, self.show_notes, self.moments = None, "", []
        if args.show:  # show night: the notes the studio prepared earlier, from MongoDB Atlas
            from db import db
            show = db()["shows"].find_one({"name": args.show})
            if not show:
                raise SystemExit(f"no show called {args.show!r} in Atlas; prepare it with scripts/prepare_show.py")
            self.plan, self.show_notes = show["plan"], show["show_notes"]
            self.moments = [tuple(m) for m in show["key_moments"]]
            print(f"show notes loaded from Atlas: {args.show}")
        elif args.rehearsal:  # or prepare them now from the studio's rehearsal video
            from show_notes import prepare
            self.plan, self.moments, self.show_notes = prepare(args.rehearsal, args.style)
        if self.plan:
            gaps = [g for g in self.song_map["clean_spaces"] if g]
            print(f"show notes ready: {self.plan['style']['name']}, {len(self.moments)} key moments, {len(gaps)} gaps in the song")
        self.engine = LiveEngine(self) if args.engine == "live" else None

    # ---------- per frame ----------
    def track(self, frame, t):
        r = self.pose.track(frame, imgsz=640, conf=0.3, persist=True, verbose=False, device=DEVICE)[0]
        if len(r.boxes):
            boxes, xy, conf = r.boxes.xyxy.cpu().numpy(), r.keypoints.xy.cpu().numpy(), r.keypoints.conf.cpu().numpy()
            k = int(np.argmax((boxes[:, 3] - boxes[:, 1]) * conf.mean(axis=1)))  # the biggest, clearest person
            with self.lock:
                self.path[round(t, 3)] = [(boxes[k], xy[k], conf[k], None, 1.0)]
            return xy[k], conf[k]
        return None

    def remember(self, frame, t):
        with self.lock:
            if not self.frames or t - self.frames[-1][0] >= 1 / CLIP_FPS:
                self.frames.append((t, jpeg(frame)))
                if self.engine:
                    self.engine.send("frame", jpeg(frame, 384))
            self.frames = [(ft, f) for ft, f in self.frames if ft > t - max(CLIP_SECONDS, NOTES_EVERY) - 2]
            self.path = {pt: p for pt, p in self.path.items() if pt > t - 30}

    def schedule(self, t):
        """At each phrase end (or, with show notes, at each gap in the song the notes identified), think about the
        last few seconds in the background so the video never stalls."""
        if self.show_notes:
            for n, gap in enumerate(self.song_map["clean_spaces"]):
                if gap and gap[0] <= t < gap[0] + 1.5 and n not in self.done_phrases:
                    self.done_phrases.add(n)
                    threading.Thread(target=self.describe, args=(n, max(0.0, gap[0] - CLIP_SECONDS), gap[0]),
                                     daemon=True).start()
            if t - self.last_notes >= NOTES_EVERY and t > NOTES_EVERY / 2:
                self.last_notes = t
                threading.Thread(target=self.direct, args=(t,), daemon=True).start()
            return
        for n, (start, end) in enumerate(self.song_map["phrases"]):
            lead = 0.0 if self.engine else 0.5  # the fallback starts thinking just before the phrase ends
            if end - lead <= t and n not in self.done_phrases and end > t - 2:
                self.done_phrases.add(n)
                threading.Thread(target=self.describe, args=(n, start, end), daemon=True).start()
        if t - self.last_notes >= NOTES_EVERY and t > NOTES_EVERY / 2:
            self.last_notes = t
            threading.Thread(target=self.direct, args=(t,), daemon=True).start()

    # ---------- Gemini, on its feet ----------
    def describe(self, n, start, end):
        asked = time.perf_counter()
        with self.lock:
            path = dict(self.path)
            clip = [(ft, f) for ft, f in self.frames if end - CLIP_SECONDS <= ft <= end]
            said, notes = list(self.said[-6:]), self.notes
        sizes = [p[0][0][3] - p[0][0][1] for pt, p in path.items() if start <= pt < end]
        if not clip or not sizes:
            return
        features = phrase_features(path, float(np.median(sizes)), True, start, end, n, beats=self.song_map["beats"])
        if self.engine:  # Gemini Live speaks straight away; the checker reviews the line as it's said
            measured = {k: features.get(k) for k in ("travel", "turns", "rotation", "facing", "max_rise", "lowest_level",
                                                    "stillness", "footwork") if features.get(k) not in (None, "")}
            prompt = f"Now ({start:.0f}-{end:.0f} s in the song). Measured: {json.dumps(measured, default=float)}."
            if self.plan:
                expected = [what for mt, what in self.moments if start - 2 <= mt <= end + 2]
                section = next((sec["label"] for sec in self.plan["sections"] if sec["start"] <= end < sec["end"]), "")
                prompt += (f" In rehearsal this was the section '{section}'"
                           + (f", with: {'; '.join(expected)}" if expected else "")
                           + ". Describe what the dancer actually does now.")
            if self.feedback:
                prompt += " " + self.feedback
            if notes and notes != getattr(self, "notes_sent", ""):
                prompt += f" Director's notes: {notes}"
                self.notes_sent = notes
            self.feedback = ""
            self.engine.send("turn", {"n": n, "start": start, "end": end, "features": features, "prompt": prompt})
            return
        parts = []
        for ft, f in clip:
            parts += [f"{ft:.1f} s:", types.Part.from_bytes(data=f, mime_type="image/jpeg")]
        context = (f"Pose measurements for {start:.1f}-{end:.1f} s: {json.dumps(features, default=float)}\n"
                   f"Already said: {said or 'nothing yet'}\n"
                   f"Director's notes: {notes or 'none yet'}"
                   + (f"\nThe style is {self.args.style}." if self.args.style else "")
                   + ("\nVocabulary vetted by dancers (use a term only if what you see matches it):\n"
                      + "\n".join(self.glossary) if self.glossary else ""))
        try:
            r = with_retry(lambda: director.client().models.generate_content(
                model=WRITER, contents=[LIVE_BRIEF, *parts, context],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={"type": "object", "properties": {"line": {"type": "string", "nullable": True}}},
                    thinking_config=types.ThinkingConfig(thinking_level="low"))))
            line = json.loads(r.text).get("line")
        except Exception as e:  # a failed call means one silent phrase, never a crash
            print(f"phrase {n}: writer failed ({type(e).__name__})")
            return
        if not line:
            print(f"phrase {n} ({start:.0f}-{end:.0f}s): silence")
            return
        verdict = check(line, features, max_words=10)
        if not verdict.passed:
            print(f"phrase {n}: checker rejected \"{line}\" ({verdict.reason})")
            self.badge = (f'checker rejected "{line}": {verdict.reason}', self.mixer.now() + 4)
            return
        wav = Path(tempfile.gettempdir()) / f"unseen-live-{n}.wav"
        try:
            speech._synthesise(line, wav)
            speech._tighten(wav)
        except Exception as e:
            print(f"phrase {n}: voice failed ({type(e).__name__})")
            return
        if self.mixer.now() - end > 8:  # too late to be about what's happening now
            print(f"phrase {n}: dropped, ready too late")
            return
        at, seconds = self.mixer.say(wav)
        with self.lock:
            self.said.append(line)
            self.log.append({"phrase": n, "line": line, "at": at, "seconds": seconds, "wav": str(wav),
                             "latency": round(time.perf_counter() - asked, 1)})
        self.caption = (line, at, at + seconds + 0.4)
        print(f"phrase {n} ({start:.0f}-{end:.0f}s): \"{line}\"  ready in {time.perf_counter() - asked:.1f}s, "
              f"spoken at {at:.1f}s")

    def spoken(self, turn):
        """A Live line has been said: check it against the measurements; a wrong claim is flagged on screen and fed
        back so the next line puts it right."""
        line = turn["words"].strip()
        if not line or turn["at"] is None:
            return
        verdict = check(line, turn["features"], max_words=12)
        if not verdict.passed:
            self.badge = (f'checker flagged "{line}": {verdict.reason}', self.mixer.now() + 4)
            self.feedback = f'Your last line ("{line}") was wrong: {verdict.reason}.'
        wav = Path(tempfile.gettempdir()) / f"unseen-live-{turn['n']}.wav"
        with wave.open(str(wav), "wb") as f:
            f.setnchannels(1), f.setsampwidth(2), f.setframerate(24000), f.writeframes(bytes(turn["pcm"]))
        with self.lock:
            self.said.append(line)
            self.log.append({"phrase": turn["n"], "line": line, "at": turn["at"], "seconds": turn["end"] - turn["at"],
                             "wav": str(wav), "latency": turn["latency"], "checker": verdict.reason or "ok"})
        print(f"phrase {turn['n']} ({turn['start']:.0f}-{turn['phrase_end']:.0f}s): \"{line}\"  first sound "
              f"{turn['latency']:.2f}s after asking" + ("" if verdict.passed else f"  [checker: {verdict.reason}]"))

    def direct(self, t):
        with self.lock:
            stretch = [(ft, f) for ft, f in self.frames if ft > t - NOTES_EVERY]  # 2 frames a second
            previous = self.notes
        if not stretch:
            return
        parts = []
        for ft, f in stretch:
            parts += [f"{ft:.1f} s:", types.Part.from_bytes(data=f, mime_type="image/jpeg")]
        try:
            r = with_retry(lambda: director.client().models.generate_content(
                model=DIRECTOR, contents=[NOTES_BRIEF, *parts, f"Your previous notes:\n{previous or 'none yet'}"
                                          + (f"\nThe style is {self.args.style}." if self.args.style else "")],
                config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="low"))))
            with self.lock:
                self.notes = r.text.strip()
            print(f"director at {t:.0f}s:\n{self.notes}\n")
        except Exception as e:
            print(f"director failed ({type(e).__name__})")

    # ---------- run ----------
    def run(self):
        args = self.args
        source = int(args.camera) if str(args.camera).isdigit() else args.camera
        cap = cv2.VideoCapture(source)
        from_file = not isinstance(source, int)
        file_fps = cap.get(cv2.CAP_PROP_FPS) or 30
        writer, frame_no, shown = None, 0, 0
        if self.engine:
            self.engine.start()
            print("connected to Gemini Live")
        self.mixer.start()
        print(f"music: {self.song_map['bpm']} bpm, {len(self.song_map['phrases'])} phrases. Press q to stop.")
        try:
            while True:
                t = self.mixer.now()
                if from_file:  # keep the stand-in camera in step with the song: skip frames if behind, wait if ahead
                    target = int(t * file_fps)
                    if frame_no > target:
                        time.sleep(0.005)
                        continue
                    ok = True
                    while ok and frame_no <= target:
                        ok = cap.grab()
                        frame_no += 1
                    ok, frame = cap.retrieve() if ok else (False, None)
                else:
                    ok, frame = cap.read()
                if not ok or t >= len(self.mixer.song) / RATE or (args.seconds and t >= args.seconds):
                    break
                person = self.track(frame, t)
                self.remember(frame, t)
                self.schedule(t)
                if person is not None:
                    draw_skeleton(frame, person[0], person[1], LEAD_COLOUR, max(2, frame.shape[0] // 240))
                caption = self.caption[0] if self.caption and self.caption[1] <= t <= self.caption[2] else None
                badge = self.badge[0] if self.badge and t <= self.badge[1] else None
                frame = draw_text(frame, caption, badge)
                if args.record:
                    if writer is None:
                        writer = cv2.VideoWriter(str(Path(args.record).with_suffix(".silent.mp4")),
                                                 cv2.VideoWriter_fourcc(*"mp4v"), 15, (frame.shape[1], frame.shape[0]))
                    while shown < int(t * 15):  # constant 15 fps in the recording, whatever the live rate
                        writer.write(frame)
                        shown += 1
                if not args.headless:
                    cv2.imshow("Unseen Steps live", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
        finally:
            self.mixer.stop()
            cap.release()
            if writer:
                writer.release()
                self.mux(t)
            cv2.destroyAllWindows()
            print(f"\n{len(self.log)} lines spoken; median latency "
                  f"{np.median([l['latency'] for l in self.log]) if self.log else 0:.2f} s from asking to the first sound")

    def mux(self, until):
        """The recording with the song and every spoken line mixed in, as it was heard."""
        silent = Path(self.args.record).with_suffix(".silent.mp4")
        inputs = ["-i", str(silent), "-i", self.args.song]
        graph = ["[1:a]volume=0.85[m]"]
        for k, l in enumerate(self.log):
            inputs += ["-i", l["wav"]]
            graph.append(f"[{k + 2}:a]adelay=delays={int(l['at'] * 1000)}:all=1,volume=1.3[n{k}]")
        graph.append("[m]" + "".join(f"[n{k}]" for k in range(len(self.log)))
                     + f"amix=inputs={len(self.log) + 1}:normalize=0:duration=first[a]")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(graph),
                        "-map", "0:v", "-map", "[a]", "-t", f"{until:.2f}", "-c:v", "libx264", "-crf", "22",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", self.args.record], check=True)
        silent.unlink()
        Path(self.args.record).with_suffix(".json").write_text(json.dumps(self.log, indent=2))
        print(f"recorded: {self.args.record}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--song", required=True, help="the music to play (mp3, wav, or a video's soundtrack)")
    parser.add_argument("--camera", default="0", help="camera index, or a video file to stand in for the camera")
    parser.add_argument("--beats-per-bar", type=int, default=4)
    parser.add_argument("--model", default="yolo11n-pose.pt", help="pose model; bigger is better if it stays above ~10 fps")
    parser.add_argument("--style", help="the style, if known (a hint for Gemini; also loads its glossary)")
    parser.add_argument("--terms", choices=["beginner", "professional"], default="professional")
    parser.add_argument("--record", help="save the session (video, music and narration) to this .mp4")
    parser.add_argument("--headless", action="store_true", help="no window (for testing)")
    parser.add_argument("--seconds", type=float, help="stop after this many seconds")
    parser.add_argument("--mute", action="store_true", help="keep time without playing sound (for tests)")
    parser.add_argument("--show", help="the name of a show whose notes were prepared earlier and stored in Atlas "
                        "(scripts/prepare_show.py)")
    parser.add_argument("--rehearsal", help="the studio's rehearsal video of this piece: Argon prepares show notes "
                        "from it before the show, and narration goes in the gaps in the song")
    parser.add_argument("--engine", choices=["live", "flash"], default="live",
                        help="live: Gemini Live watches and speaks (~0.7 s); flash: write then TTS (~5 s)")
    Live(parser.parse_args()).run()


if __name__ == "__main__":
    main()
