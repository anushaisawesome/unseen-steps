// Measurements for one phrase, from the pose samples: the same features and thresholds as phrase_features in
// scripts/killtest.py (all in seconds, so any frame rate gives the same answers), in the shape checker.py reads.
// Directions are as the audience sees them: the camera faces the dancer like the audience does.

const NOSE = 0, L_EYE = 1, R_EYE = 2, L_SHO = 5, R_SHO = 6, L_WRI = 9, R_WRI = 10, L_HIP = 11, R_HIP = 12,
  L_ANK = 15, R_ANK = 16;
const TURN_HOLD = 0.3;   // seconds a new facing must last to count as a turn
const FACING_HOLD = 0.5; // seconds a change of facing must last to be an event

const median = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; };
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p / 100 * s.length))]; };
const mid = (p, a, b) => [(p.kp[a][0] + p.kp[b][0]) / 2, (p.kp[a][1] + p.kp[b][1]) / 2];

function facingOf(p, size) {
  const k = p.kp;
  if (Math.min(k[L_SHO][2], k[R_SHO][2]) < 0.4) return "unclear";
  const width = (k[L_SHO][0] - k[R_SHO][0]) / size;
  const face = k[NOSE][2] > 0.5 && Math.max(k[L_EYE][2], k[R_EYE][2]) > 0.5;
  if (Math.abs(width) < 0.07) return k[NOSE][2] > 0.4 ? "side-on" : "unclear";
  if (width > 0 && face) return "facing us";
  if (width < 0 && !face) return "back to us";
  return "unclear";
}

// samples: [{t, pose: {box, kp} | null}] for the phrase; expectedRate: pose samples per second we managed.
export function phraseFeatures(samples, start, end, phrase, expectedRate) {
  const seen = samples.filter((s) => s.pose);
  const base = { phrase, start: +start.toFixed(1), end: +end.toFixed(1), people: 1 };
  if (seen.length < 0.3 * (end - start) * expectedRate || seen.length < 4) return { ...base, tracking: "poor" };

  const t = seen.map((s) => s.t), P = seen.map((s) => s.pose);
  const size = median(P.map((p) => p.box[3] - p.box[1]));
  const hips = P.map((p) => mid(p, L_HIP, R_HIP));

  // speed (body heights per second) and stillness (share of time nearly still)
  const speeds = [];
  for (let i = 1; i < hips.length; i++) {
    const dt = Math.max(t[i] - t[i - 1], 1e-3);
    speeds.push(Math.hypot(hips[i][0] - hips[i - 1][0], hips[i][1] - hips[i - 1][1]) / size / dt);
  }
  const stillness = speeds.filter((v) => v < 0.15).length / Math.max(1, speeds.length);

  // travel: hip position over the first and last half second
  const near = (from, to) => median(hips.filter((_, i) => t[i] >= from && t[i] <= to).map((h) => h[0]));
  const travelX = (near(t.at(-1) - 0.5, t.at(-1)) - near(t[0], t[0] + 0.5)) / size;
  const travel = travelX < -0.5 ? "left" : travelX > 0.5 ? "right" : "none";

  // rise (jumps): how far the hips go above their usual height; level: leg length when ankles are visible
  const hipY = hips.map((h) => h[1]);
  // 95th percentile, as in killtest.py: one jittery frame isn't a jump
  const maxRise = pct(hipY.map((y) => (median(hipY) - y) / size), 95);
  // Only joints YOLO can actually see count: out of frame or hidden, it still guesses positions.
  const legsInView = P.filter((p) => Math.min(p.kp[L_ANK][2], p.kp[R_ANK][2], p.kp[13][2], p.kp[14][2]) > 0.5).length / P.length >= 0.5;
  const legs = P.filter((p) => Math.min(p.kp[L_ANK][2], p.kp[R_ANK][2]) > 0.5)
    .map((p) => ((p.kp[L_ANK][1] + p.kp[R_ANK][1]) / 2 - (p.kp[L_HIP][1] + p.kp[R_HIP][1]) / 2) / size);
  const lowest = !legsInView || legs.length < 5 ? "standing" : pct(legs, 5) < 0.15 ? "floor" : pct(legs, 5) < 0.3 ? "low" : "standing";

  // arms above the head
  const armsUp = P.filter((p) => p.kp[L_WRI][2] > 0.4 && p.kp[R_WRI][2] > 0.4 &&
    p.kp[L_WRI][1] < p.kp[NOSE][1] && p.kp[R_WRI][1] < p.kp[NOSE][1]).length / P.length;

  const events = [];
  // turns: the shoulders swap sides and stay swapped for TURN_HOLD; two swaps make one full turn
  let swaps = 0, current = null, since = null;
  P.forEach((p, i) => {
    // Only trust which shoulder is which when they're clearly apart: side-on, they overlap on screen and
    // jitter would look like a swap (a false turn).
    const width = (p.kp[L_SHO][0] - p.kp[R_SHO][0]) / size;
    if (Math.abs(width) < 0.1 || Math.min(p.kp[L_SHO][2], p.kp[R_SHO][2]) < 0.5) return;
    const s = Math.sign(width);
    if (current === null) current = s;
    else if (s !== current) {
      since ??= t[i];
      if (t[i] - since >= TURN_HOLD) { swaps++; current = s; since = null; events.push(`${(t[i] - start).toFixed(1)}s: turn`); }
    } else since = null;
  });
  const turns = Math.floor((swaps + 1) / 2);

  // facing, and changes of facing that last half a second
  const faces = P.map((p) => facingOf(p, size));
  const counted = faces.filter((f) => f !== "unclear");
  const facing = counted.length ? [...new Set(counted)].sort((a, b) => counted.filter((f) => f === b).length - counted.filter((f) => f === a).length)[0] : "unclear";
  let cur = faces[0], pending = null;
  faces.forEach((f, i) => {
    if (f === cur || f === "unclear") { pending = null; return; }
    if (!pending || pending[1] !== f) { pending = [t[i], f]; return; }
    if (t[i] - pending[0] >= FACING_HOLD) { cur = f; pending = null; events.push(`${(t[i] - start).toFixed(1)}s: now ${f}`); }
  });

  // arm raised high, and kicks (ankle above knee), lasting at least min seconds
  const intervals = (flags, label, min) => {
    let begin = null;
    flags.forEach((f, i) => {
      if (f && begin === null) begin = t[i];
      if (!f && begin !== null) { if (t[i] - begin >= min) events.push(`${(begin - start).toFixed(1)}s: ${label}`); begin = null; }
    });
  };
  const seenY = (p, joints, min) => joints.filter((j) => p.kp[j][2] > min).map((j) => p.kp[j][1]);
  intervals(P.map((p) => {
    const wrists = seenY(p, [L_WRI, R_WRI], 0.4);
    return p.kp[NOSE][2] > 0.4 && wrists.length > 0 && Math.min(...wrists) < p.kp[NOSE][1];
  }), "arm raised high", 0.25);
  if (legsInView) {
    intervals(P.map((p) => {
      const ankles = seenY(p, [L_ANK, R_ANK], 0.5), knees = seenY(p, [13, 14], 0.5);
      return ankles.length > 0 && knees.length > 0 && Math.min(...ankles) < Math.max(...knees);
    }), "leg kick or high leg", 0.1);
  }
  events.sort((a, b) => parseFloat(a) - parseFloat(b));

  const coverage = seen.length / Math.max(1, (end - start) * expectedRate);
  // Confidence of the head, shoulders, arms and hips: a webcam often cuts off the legs, which shouldn't silence it.
  const conf = P.reduce((s, p) => s + p.kp.slice(0, 13).reduce((q, k) => q + k[2], 0) / 13, 0) / P.length;
  const tracking = conf > 0.5 && coverage > 0.7 ? "good" : conf > 0.3 && coverage > 0.4 ? "ok" : "poor";
  return {
    ...base, tracking,
    speed: +median(speeds).toFixed(2), max_rise: +maxRise.toFixed(3), lowest_level: lowest, travel,
    turns, rotation: null, arms_up: +armsUp.toFixed(2), stillness: +stillness.toFixed(2), facing,
    legs_in_view: legsInView,
    events: events.slice(0, 10),
  };
}
