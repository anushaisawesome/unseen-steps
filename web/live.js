// Live venue loop, the website version of scripts/live.py: camera -> YOLO pose on this device -> every WINDOW
// seconds (one request at a time), the last CONTEXT seconds go to /api/describe as frames (FRAME_RATE a second)
// plus pose measurements, what's been said and the director's notes -> Gemini writes a line, checker.py vets it
// -> it's spoken if still current, else skipped. In the background, /api/notes has Argon update its running notes
// from the last NOTES_EVERY seconds. Camera frames are sent to Gemini; nothing is stored.

import { loadPose, detect } from "./pose.js";
import { phraseFeatures } from "./features.js";

// No music map live: every WINDOW seconds (as soon as the previous request is back, without waiting for speech),
// describe the last CONTEXT seconds (overlapping). STALE: a line about movement that ended longer ago than this is
// skipped, never spoken late. CONTEXT, FRAME_RATE and NOTES_EVERY match scripts/live.py.
const WINDOW = 1.5, CONTEXT = 4, STALE = 3, FRAME_RATE = 2, NOTES_EVERY = 20, FRAME_WIDTH = 512;
const BONES = [[5, 7], [7, 9], [6, 8], [8, 10], [5, 6], [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [0, 5], [0, 6]];
const $ = (id) => document.getElementById(id);
const video = $("camera"), overlay = $("overlay"), draw = overlay.getContext("2d");

let running = false, stream = null, t0 = 0, samples = [], phraseStart = 0, phraseN = 0;
let frames = [], notes = "", notesBusy = false, lastNotes = 0;  // {t, jpeg base64} at FRAME_RATE; Argon's notes
const snap = document.createElement("canvas"), snapCtx = snap.getContext("2d");
let previous = [], playing = null, pending = null, speechToken = 0, waiting = false, speaking = false, smoothed = null, lastT = 0, lastError = "", lastLineAt = null;
let failures = 0, wakeLock = null;
const BRIEF_GAP = 8;  // seconds: in brief mode, at most one line this often, so the music has more room
const SMOOTH = 0.1;  // seconds: keypoint smoothing time constant (steadier turns and travel, still follows jumps)

const saved = (() => { try { return JSON.parse(localStorage.getItem("unseen-steps-live") || "{}"); } catch { return {}; } })();
for (const k of ["voice", "vol", "style", "rate"]) if (saved[k] !== undefined) $(k).value = saved[k];
$("announce").checked = !!saved.announce;
if (saved.amount === "brief") $("amount-brief").checked = true;
const amount = () => document.querySelector('input[name="amount"]:checked').value;
const rate = () => +$("rate").value || 1;
function remember() {
  try {
    localStorage.setItem("unseen-steps-live", JSON.stringify({ voice: $("voice").value, vol: $("vol").value, style: $("style").value,
      rate: $("rate").value, amount: amount(), announce: $("announce").checked }));
  } catch {}
}
for (const id of ["voice", "vol", "style", "announce", "rate", "amount-detailed", "amount-brief"]) $(id).addEventListener("change", remember);
const volumeText = () => $("vol").setAttribute("aria-valuetext", `${Math.round(+$("vol").value * 100)}%`);
$("vol").addEventListener("input", volumeText);
volumeText();

const status = (text) => { $("status").textContent = text; };

$("setup").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (running) return stop("Stopped.");
  $("start").disabled = true;
  try {
    status("Asking for the camera…");
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } }, audio: false });
    video.srcObject = stream;
    await video.play();
    $("stage").hidden = false;
    const backend = await loadPose(status);
    running = true;
    t0 = performance.now() / 1000;
    samples = []; phraseStart = 0; phraseN = 0; previous = []; waiting = false; speaking = false; pending = null;
    frames = []; notes = ""; notesBusy = false; lastNotes = 0; $("notes").textContent = "";
    failures = 0;
    $("start").textContent = "Stop listening";
    status(`Listening. Watching the dancer (pose on ${backend === "webgpu" ? "the graphics chip" : "the processor"}); the first description comes in a few seconds.`);
    keepAwake();
    lockScreenControls();
    loop();
  } catch (err) {
    stop(err.name === "NotAllowedError" ? "Camera access was refused. Allow the camera in your browser's site settings, then try again."
      : `Couldn't start: ${err.message}`);
  } finally {
    $("start").disabled = false;
  }
});

function stop(message) {
  running = false;
  pending = null; speaking = false; speechToken++;
  playing?.pause?.(); speechSynthesis.cancel();
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  $("stage").hidden = true;
  $("start").textContent = "Start listening";
  wakeLock?.release?.().catch(() => {});
  wakeLock = null;
  if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "none";
  status(message);
}

// Keep the screen awake while describing (the camera stops when a phone locks). Re-asked when the page comes back.
async function keepAwake() {
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch { wakeLock = null; }
}
document.addEventListener("visibilitychange", () => {
  if (!running) return;
  if (document.visibilityState === "visible") { keepAwake(); status("Listening again."); }
  else status("Paused while the screen is off. It picks up again when you come back.");
});

// Headphone and lock-screen controls, where the browser offers them: pause or stop ends the description.
function lockScreenControls() {
  if (!("mediaSession" in navigator)) return;
  try {
    navigator.mediaSession.metadata = new MediaMetadata({ title: "Live audio description", artist: "Unseen Steps",
      album: $("style").value.trim() || "Dance" });
    navigator.mediaSession.playbackState = "playing";
    for (const action of ["pause", "stop"]) navigator.mediaSession.setActionHandler(action, () => running && stop("Stopped."));
  } catch {}
}

// The narrator is a web request every second or two; if it fails, keep watching and say so once, then say when it's back.
function reached(ok, why = "") {
  if (ok) {
    if (failures) status("Connected to the narrator again.");
    failures = 0;
  } else if (++failures === 1) {
    status(`Lost the connection to the narrator${why ? ` (${why})` : ""}. Still watching, and trying again.`);
  }
}

async function loop() {
  while (running) {
    if (video.readyState >= 2) {
      const t = performance.now() / 1000 - t0;
      let pose = null;
      try { pose = smooth(await detect(video), t); } catch (err) { lastError = err.message; console.error(err); }
      samples.push({ t, pose });
      keepFrame(t);
      drawPose(pose);
      readout(t);
      if (!waiting && t - phraseStart >= WINDOW) endPhrase(t);
      if (!notesBusy && t - lastNotes >= NOTES_EVERY && t > NOTES_EVERY / 2) direct(t);
    }
    await new Promise((r) => requestAnimationFrame(r));
  }
}

// FRAME_RATE small JPEGs a second, kept for the last NOTES_EVERY seconds (what the writer and director see).
function keepFrame(t) {
  if (frames.length && t - frames.at(-1).t < 1 / FRAME_RATE) return;
  snap.width = FRAME_WIDTH;
  snap.height = Math.round(video.videoHeight * FRAME_WIDTH / video.videoWidth);
  snapCtx.drawImage(video, 0, 0, snap.width, snap.height);
  frames.push({ t: +t.toFixed(2), jpeg: snap.toDataURL("image/jpeg", 0.8).split(",")[1] });
  frames = frames.filter((f) => f.t > t - NOTES_EVERY - 2);
}

// Argon's running notes (style, signature, motifs, what just changed), in the background as in live.py.
async function direct(t) {
  notesBusy = true; lastNotes = t;
  try {
    const res = await fetch("/api/notes", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frames: frames.filter((f) => f.t > t - NOTES_EVERY), notes, style: $("style").value.trim() }),
    });
    const out = await res.json();
    if (res.ok) { notes = out.notes || notes; $("notes").textContent = notes; } else lastError = out.error;
  } catch (err) { lastError = err.message; }
  notesBusy = false;
}

// Exponential smoothing in seconds (frame-rate independent), per keypoint, only between confident readings.
function smooth(pose, t) {
  if (!pose) { smoothed = null; return null; }
  if (smoothed) {
    const a = 1 - Math.exp(-(t - lastT) / SMOOTH);
    pose.kp = pose.kp.map((k, i) => {
      const s = smoothed.kp[i];
      return k[2] > 0.3 && s[2] > 0.3 ? [s[0] + a * (k[0] - s[0]), s[1] + a * (k[1] - s[1]), k[2]] : k;
    });
  }
  smoothed = pose; lastT = t;
  return pose;
}

// What the system is doing right now, for whoever sets up the camera.
let lastReadout = 0;
function readout(t) {
  if (t - lastReadout < 1) return;
  lastReadout = t;
  const recent = samples.filter((s) => s.t > t - 2);
  const fps = recent.length / 2;
  const inView = recent.length ? Math.round(100 * recent.filter((s) => s.pose).length / recent.length) : 0;
  const parts = [`${fps.toFixed(0)} frames a second`, `dancer in view ${inView}% of the last 2 s`];
  if (fps < 5) parts.push("slow device: tracking will be rough");
  if (inView < 50) parts.push("get the whole body in frame, with more light if you can");
  if (lastLineAt !== null) parts.push(`last line ${Math.round(t - lastLineAt)} s ago`);
  if (lastError) parts.push(`last error: ${lastError}`);
  $("diag").textContent = parts.join(" · ");
}

function drawPose(pose) {
  overlay.width = video.videoWidth; overlay.height = video.videoHeight;
  draw.clearRect(0, 0, overlay.width, overlay.height);
  if (!pose) return;
  draw.lineWidth = Math.max(3, overlay.width / 200);
  draw.strokeStyle = "#ff6fd8";
  for (const [a, b] of BONES) {
    const p = pose.kp[a], q = pose.kp[b];
    if (p[2] < 0.3 || q[2] < 0.3) continue;
    draw.beginPath(); draw.moveTo(p[0], p[1]); draw.lineTo(q[0], q[1]); draw.stroke();
  }
}

async function endPhrase(t) {
  const start = Math.max(0, t - CONTEXT), n = phraseN++;
  const window = samples.filter((s) => s.t >= start && s.t < t);
  samples = samples.filter((s) => s.t >= t - CONTEXT);  // what the next, overlapping window needs
  phraseStart = t;
  const rate = window.length / Math.max(0.5, t - start);
  const features = phraseFeatures(window, start, t, n, rate);
  const entry = addLog(start, features);
  if (features.tracking === "poor") {
    entry.say("(silent: no dancer clearly in view)");
    return;
  }
  waiting = true;
  try {
    const res = await fetch("/api/describe", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice: $("voice").value, features, said: previous, notes, style: $("style").value.trim(),
                             frames: frames.filter((f) => f.t >= start && f.t <= t) }),
    });
    const out = await res.json();
    if (!res.ok) { lastError = out.error; reached(false, out.error); entry.say(`(silent: ${out.error})`); return; }
    reached(true);
    entry.say(out.line || "(silent: nothing new to say)", out.attempts);
    if (out.line) offer({ line: out.line, audio: out.audio, end: t, entry });
  } catch (err) {
    lastError = err.message;
    reached(false);
    entry.say(`(silent: couldn't reach the narrator, ${err.message})`);
  } finally {
    waiting = false;
  }
}

// Live means current: a line is spoken only if the movement it describes ended at most STALE seconds ago.
// While a line is being spoken, only the newest finished line waits; older ones are skipped.
const now = () => performance.now() / 1000 - t0;
const fresh = (item) => now() - item.end <= STALE;
function offer(item) {
  if (amount() === "brief" && lastLineAt !== null && now() - lastLineAt < BRIEF_GAP) return item.entry.mark("Skipped: brief mode, leaving room for the music");
  if (!speaking) return fresh(item) ? speak(item) : item.entry.mark("Skipped: too late");
  pending?.entry.mark("Skipped: a newer line came in");
  pending = item;
}
function next() {
  speaking = false;
  const item = pending;
  pending = null;
  if (item) fresh(item) ? speak(item) : item.entry.mark("Skipped: too late");
}

function speak(item) {
  const { line, audio } = item;
  item.entry.mark("Spoken");
  lastLineAt = now();
  previous = [...previous, line].slice(-5);
  $("now").textContent = line;
  if ($("announce").checked) $("live").textContent = line;
  const volume = +$("vol").value;
  speaking = true;
  const token = ++speechToken;
  const done = () => { if (token === speechToken && speaking) next(); };
  // Backstop: some browsers never report the end of speech; a line takes about words / 3 seconds at this rate.
  setTimeout(done, (line.split(/\s+/).length / (3 * rate()) + 1) * 1000);
  if (audio) {
    playing = new Audio(`data:audio/wav;base64,${audio}`);
    playing.volume = volume;
    playing.playbackRate = rate();
    playing.onended = playing.onerror = done;
    playing.play().catch(done);
  } else {
    const u = new SpeechSynthesisUtterance(line);
    u.volume = volume; u.lang = "en-GB"; u.rate = Math.min(2, 1.25 * rate());
    u.onend = u.onerror = done;
    speechSynthesis.speak(u);
    playing = { pause: () => speechSynthesis.cancel() };
  }
}

function addLog(start, f) {
  const li = document.createElement("li");
  const measured = f.tracking === "poor" ? "dancer not clearly in view"
    : [`tracking ${f.tracking}`, f.travel !== "none" ? `travels ${f.travel}` : "stays in place",
       f.turns ? `${f.turns} turn${f.turns > 1 ? "s" : ""}` : null, f.max_rise >= 0.05 ? "hips rise" : null,
       f.lowest_level === "floor" ? "goes to the floor" : f.lowest_level === "low" ? "goes low" : null, f.facing !== "unclear" ? f.facing : null,
       f.stillness > 0.5 ? "mostly still" : null].filter(Boolean).join(", ");
  li.innerHTML = `<span class="stamp">${Math.floor(start / 60)}:${String(Math.floor(start % 60)).padStart(2, "0")}</span>
    <div class="entry"><span class="text">Writing…</span><p class="hint"></p></div>`;
  li.querySelector(".hint").textContent = `Measured: ${measured}.`;
  $("log").prepend(li);
  while ($("log").children.length > 40) $("log").lastElementChild.remove();
  return {
    mark(label) {
      const tag = document.createElement("span");
      tag.className = label === "Spoken" ? "verdict ok" : "verdict no";
      tag.textContent = label;
      li.querySelector("div").prepend(tag);
    },
    say(text, attempts = []) {
      li.querySelector(".text").textContent = text;
      for (const a of attempts.filter((a) => !a.passed)) {
        const p = document.createElement("p");
        p.className = "draft";
        p.innerHTML = `<span class="verdict no">Rejected draft</span> <s></s><br><span></span>`;
        p.querySelector("s").textContent = a.draft;
        p.lastElementChild.textContent = `Why: ${a.reason}.`;
        li.querySelector("div").append(p);
      }
    },
  };
}
