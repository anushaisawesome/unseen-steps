// Demo player: the video carries the picture and music; the narration is a separate audio track kept in sync,
// so each has its own volume. Captions, transcript and the reveal's line log all come from data/ballet.json.

const $ = (id) => document.getElementById(id);
const video = $("video"), narration = $("narration");
const data = await (await fetch("data/ballet.json?v=3")).json();
const spoken = data.lines.filter((l) => l.at !== null);

const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const words = (s) => `${Math.round(s)} second${Math.round(s) === 1 ? "" : "s"}`;

// ---- sync the narration to the video (the video is the clock)
function sync(force) {
  if (force || Math.abs(narration.currentTime - video.currentTime) > 0.15) narration.currentTime = video.currentTime;
}
video.addEventListener("play", () => { sync(true); narration.play().catch(() => {}); setPlaying(true); });
video.addEventListener("pause", () => { narration.pause(); setPlaying(false); });
video.addEventListener("seeked", () => sync(true));
// the last line may run a moment past the picture: let it finish rather than cut it off mid-sentence
video.addEventListener("ended", () => { setPlaying(false); });
video.addEventListener("timeupdate", () => { if (!video.paused) sync(false); update(); });

function setPlaying(on) {
  $("play").textContent = on ? "Pause" : "Play";
}
$("play").addEventListener("click", () => (video.paused ? video.play() : video.pause()));
$("player").addEventListener("keydown", (e) => {
  if (e.key === " " && !["INPUT", "SELECT", "BUTTON", "A"].includes(e.target.tagName)) {
    e.preventDefault();
    video.paused ? video.play() : video.pause();
  }
});

// ---- position slider
const seek = $("seek");
video.addEventListener("loadedmetadata", () => { seek.max = video.duration.toFixed(1); update(); });
seek.addEventListener("input", () => { video.currentTime = +seek.value; });
seek.addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    e.preventDefault();
    video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + (e.key === "ArrowRight" ? 5 : -5)));
  }
});

// ---- volumes, caption size and visibility
narration.volume = +$("vol-narration").value;
video.volume = +$("vol-music").value;
$("vol-narration").addEventListener("input", (e) => { narration.volume = +e.target.value; });
$("vol-music").addEventListener("input", (e) => { video.volume = +e.target.value; });
$("caption-size").addEventListener("change", (e) => document.documentElement.style.setProperty("--caption-size", e.target.value));
$("show-captions").addEventListener("change", (e) => { $("caption").hidden = !e.target.checked; });
for (const t of video.textTracks) t.mode = "hidden"; // drawn in our own caption box, which can be resized

// ---- transcript
const transcript = $("transcript");
spoken.forEach((l, n) => {
  const li = document.createElement("li");
  li.dataset.n = n;
  li.innerHTML = `<span class="stamp"><button type="button"><span class="sr-only">Play from </span>${fmt(l.at)}</button></span>
                  <span class="text"></span>`;
  li.querySelector(".text").textContent = l.text;
  li.querySelector("button").addEventListener("click", () => { video.currentTime = l.at; video.play(); });
  transcript.append(li);
});
const text = spoken.map((l) => `[${fmt(l.at)}] ${l.text}`).join("\n");
$("download-text").href = URL.createObjectURL(new Blob([`Unseen Steps narration: ballet solo\n\n${text}\n`], { type: "text/plain" }));

// ---- per-frame update: caption, current transcript line, screen-reader announcement
let lastLine = -1;
function update() {
  const t = video.currentTime;
  seek.value = t.toFixed(1);
  seek.setAttribute("aria-valuetext", `${words(t)} of ${words(video.duration || data.duration)}`);
  $("time").textContent = `${fmt(t)} / ${fmt(video.duration || data.duration)}`;
  const n = spoken.findIndex((l) => t >= l.at && t < l.at + l.seconds);
  $("caption").textContent = n >= 0 ? spoken[n].text : "";
  for (const li of transcript.children) li.setAttribute("aria-current", String(+li.dataset.n === n));
  if (n >= 0 && n !== lastLine && $("announce").checked && !video.paused) $("live").textContent = spoken[n].text;
  lastLine = n;
}

// ---- the reveal: beat counter and line log
const rv = $("reveal-video"), log = $("log");
const perBar = data.beats_per_bar;
$("tempo").textContent = `Music: ${Math.round(data.bpm)} beats per minute, ${perBar} beats to a bar. Lines are placed in the gaps between phrases.`;
const dots = $("beat-dots");
for (let i = 0; i < perBar; i++) dots.append(document.createElement("i"));

data.lines.forEach((l) => {
  const li = document.createElement("li");
  const when = l.at !== null ? fmt(l.at) : "–";
  const status = l.at !== null
    ? `<span class="verdict ok">Spoken</span>`
    : `<span class="verdict no">Not spoken</span>`;
  li.innerHTML = `<span class="stamp">${when}</span><div style="display:grid;gap:0.35rem">${status}<span class="text"></span></div>`;
  li.querySelector(".text").textContent = l.text || "(dropped)";
  const box = li.querySelector("div");
  for (const r of l.rejected) {
    const p = document.createElement("p");
    p.className = "draft";
    p.innerHTML = `<span class="verdict no">Rejected draft</span> <s></s><br><span></span>`;
    p.querySelector("s").textContent = r.draft;
    p.lastElementChild.textContent = `Why: ${r.reason}.`;
    box.append(p);
  }
  if (l.measured.length) {
    const ul = document.createElement("ul");
    ul.className = "measured";
    ul.setAttribute("aria-label", "Measured");
    for (const m of l.measured) {
      const item = document.createElement("li");
      item.textContent = m;
      ul.append(item);
    }
    box.append(ul);
  }
  li.dataset.at = l.at ?? "";
  li.dataset.until = l.at !== null ? l.at + l.seconds : "";
  log.append(li);
});

function revealTick() {
  const t = rv.currentTime;
  const k = data.beats.findLastIndex((b) => b <= t);
  const beat = k < 0 ? 0 : k;
  $("bar").textContent = Math.floor(beat / perBar) + 1;
  $("beat-n").textContent = (beat % perBar) + 1;
  const p = data.phrases.findLastIndex((ph) => ph[0] <= t);
  $("phrase").textContent = Math.max(1, p + 1);
  [...dots.children].forEach((d, i) => d.classList.toggle("on", k >= 0 && i === beat % perBar));
  for (const li of log.children) {
    const on = li.dataset.at !== "" && t >= +li.dataset.at && t < +li.dataset.until;
    li.setAttribute("aria-current", String(on));
  }
  if (!rv.paused) requestAnimationFrame(revealTick);
}
rv.addEventListener("play", () => requestAnimationFrame(revealTick));
rv.addEventListener("seeked", revealTick);
revealTick();
update();
