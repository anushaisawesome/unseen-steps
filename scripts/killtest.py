"""Kill test: do real pose features give specific, correct lines?

Runs YOLO-pose over a clip, follows one couple (or a soloist) by position, turns each
musical phrase into features plus a timeline of events, and runs the write-check loop
with close-up crops of the dancers. Writes an annotated video to judge the lines against.

Usage:
    python scripts/killtest.py clips/clip1.mp4 [--beats-per-bar 4] [--bars-per-phrase 4]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from music import load_audio, map_song  # noqa: E402
from narrate import describe  # noqa: E402

# COCO keypoints
NOSE, L_SHO, R_SHO, L_WRI, R_WRI, L_HIP, R_HIP, L_KNE, R_KNE, L_ANK, R_ANK = 0, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16
SAMPLE_FPS = 15
TURN_HOLD = 0.3   # seconds a new facing must last to count as a turn
APART_GAP = 0.6   # hip distance between partners, in body heights


def detect(video: str):
    """Every sampled frame: (t, [(box, keypoints xy, keypoint conf), ...])."""
    model = YOLO(str(ROOT / "models/yolo11n-pose.pt"))
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round(fps / SAMPLE_FPS))
    frames, i = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            r = model.predict(frame, imgsz=1280, conf=0.2, verbose=False, device="mps")[0]
            people = list(zip(r.boxes.xyxy.cpu().numpy(), r.keypoints.xy.cpu().numpy(),
                              r.keypoints.conf.cpu().numpy()))
            frames.append((i / fps, people))
        i += 1
    return frames


def centre(box):
    return np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])


def follow(frames):
    """Follow one couple through the clip by position, ignoring detector IDs.

    Seeds on the frame with the clearest pair of people standing together, then at each
    frame takes the detections nearest to where the couple was last seen.
    """
    seed_t, seed = None, None
    for t, people in frames:
        for a in range(len(people)):
            for b in range(a + 1, len(people)):
                pa, pb = people[a], people[b]
                h = pa[0][3] - pa[0][1]
                if np.linalg.norm(centre(pa[0]) - centre(pb[0])) < 0.8 * h:
                    score = pa[2].mean() + pb[2].mean()
                    if seed is None or score > seed[0]:
                        seed_t, seed = t, (score, pa, pb)
    if seed is None:  # no couple anywhere: follow the most confident single person
        seed_t, best = max(((t, max(p, key=lambda q: q[2].mean())) for t, p in frames if p), key=lambda x: x[1][2].mean())
        last, size, solo = centre(best[0]), best[0][3] - best[0][1], True
    else:
        last = (centre(seed[1][0]) + centre(seed[2][0])) / 2
        size, solo = seed[1][0][3] - seed[1][0][1], False

    path = {}
    for direction in (1, -1):  # grow outwards from the seed, forwards then backwards
        pos = last.copy()
        for t, people in sorted([f for f in frames if (f[0] - seed_t) * direction >= 0], key=lambda f: direction * f[0]):
            near = sorted(people, key=lambda p: np.linalg.norm(centre(p[0]) - pos))
            near = [p for p in near if np.linalg.norm(centre(p[0]) - pos) < 1.2 * size][: 1 if solo else 2]
            if near:
                path[round(t, 3)] = near
                pos = np.mean([centre(p[0]) for p in near], axis=0)
    return path, solo, size


def phrase_features(path, size, solo, start, end, phrase):
    rows = [(t, people) for t, people in sorted(path.items()) if start <= t < end]
    expected = (end - start) * SAMPLE_FPS
    base = {"phrase": phrase, "start": round(start, 1), "end": round(end, 1), "people": 1 if solo else 2}
    if len(rows) < 0.3 * expected:
        return {**base, "tracking": "poor"}

    t = np.array([r[0] for r in rows])
    lead = [r[1][0] for r in rows]
    hips = np.array([(p[1][L_HIP] + p[1][R_HIP]) / 2 for p in lead])
    centres = np.array([np.mean([(p[1][L_HIP] + p[1][R_HIP]) / 2 for p in people], axis=0) for _, people in rows])
    pairs = [people for _, people in rows if len(people) == 2]

    speed = np.linalg.norm(np.diff(centres, axis=0), axis=1) / size / np.maximum(np.diff(t), 1e-3)
    travel_x = (centres[-1, 0] - centres[0, 0]) / size
    travel = "left" if travel_x < -0.5 else "right" if travel_x > 0.5 else "none"
    rise = (np.median(hips[:, 1]) - hips[:, 1]) / size
    leg = np.array([(p[1][L_ANK][1] + p[1][R_ANK][1]) / 2 - (p[1][L_HIP][1] + p[1][R_HIP][1]) / 2 for p in lead]) / size
    lowest = "floor" if leg.min() < 0.15 else "low" if leg.min() < 0.3 else "standing"

    events = []

    # Turns: the lead's shoulders swap sides and stay swapped for TURN_HOLD seconds.
    facing = [(tt, np.sign(p[1][L_SHO][0] - p[1][R_SHO][0])) for tt, p in zip(t, lead)]
    facing = [(tt, s) for tt, s in facing if s != 0]
    turns, current, since = 0, None, None
    for tt, s in facing:
        if current is None:
            current = s
        elif s != current:
            since = since if since is not None else tt
            if tt - since >= TURN_HOLD:
                current, since = s, None
                turns += 1
                events.append((tt, "turn"))
        else:
            since = None
    turns = (turns + 1) // 2  # two swaps make one full turn; a single swap counts as a turn

    # Arms raised above the head, kicks (ankle above knee), and partners separating or joining.
    def intervals(flags, label, min_len=0.25):
        out, begin = [], None
        for tt, f in zip(t, flags):
            if f and begin is None:
                begin = tt
            if not f and begin is not None:
                if tt - begin >= min_len:
                    out.append((begin, label))
                begin = None
        return out

    events += intervals([min(p[1][L_WRI][1], p[1][R_WRI][1]) < p[1][NOSE][1] for p in lead], "arm raised high")
    events += intervals([min(p[1][L_ANK][1], p[1][R_ANK][1]) < max(p[1][L_KNE][1], p[1][R_KNE][1]) for p in lead],
                        "leg kick or high leg", 0.1)
    separation = None
    if pairs:
        gaps = [np.linalg.norm((a[1][L_HIP] + a[1][R_HIP]) / 2 - (b[1][L_HIP] + b[1][R_HIP]) / 2) / size for a, b in pairs]
        separation = "in hold" if np.median(gaps) < 0.2 else "close" if np.median(gaps) < APART_GAP else "apart"
        pair_t = [tt for tt, people in rows if len(people) == 2]
        # Only count a change of separation once it has lasted TURN_HOLD seconds.
        state, pending = gaps[0] > APART_GAP, None
        for tt, g in zip(pair_t, gaps):
            now = g > APART_GAP
            if now == state:
                pending = None
            elif pending is None:
                pending = tt
            elif tt - pending >= TURN_HOLD:
                state, pending = now, None
                events.append((tt, "partners break apart" if now else "partners come back together"))

    events = sorted(events)[:10]
    conf = np.mean([p[2].mean() for p in lead])
    coverage = len(rows) / expected
    tracking = "good" if conf > 0.5 and coverage > 0.7 else "ok" if conf > 0.35 and coverage > 0.4 else "poor"

    return {
        **base, "tracking": tracking,
        "speed": round(float(np.median(speed)), 2) if len(speed) else 0.0,
        "max_rise": round(float(np.percentile(rise, 95)), 2), "lowest_level": lowest, "travel": travel,
        "turns": turns,
        "arms_up": round(float(np.mean([min(p[1][L_WRI][1], p[1][R_WRI][1]) < p[1][NOSE][1] for p in lead])), 2),
        "stillness": round(float(np.mean(speed < 0.15)), 2) if len(speed) else 0.0, "separation": separation,
        "events": [f"{tt - start:.1f}s: {label}" for tt, label in events],
    }


def crops(video, path, start, end, n=3):
    """Close-up JPEGs of the followed dancers at evenly spaced moments in the phrase."""
    cap = cv2.VideoCapture(video)
    times = [t for t in sorted(path) if start <= t < end]
    out = []
    for t in [times[int(len(times) * k / (n + 1))] for k in range(1, n + 1)] if len(times) > n else []:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        boxes = np.array([p[0] for p in path[t]])
        x0, y0, x1, y1 = boxes[:, 0].min(), boxes[:, 1].min(), boxes[:, 2].max(), boxes[:, 3].max()
        pad = 0.4 * (y1 - y0)
        x0, y0 = int(max(0, x0 - pad)), int(max(0, y0 - pad))
        x1, y1 = int(min(frame.shape[1], x1 + pad)), int(min(frame.shape[0], y1 + pad))
        crop = cv2.resize(frame[y0:y1, x0:x1], None, fx=384 / max(1, y1 - y0), fy=384 / max(1, y1 - y0))
        out.append(cv2.imencode(".jpg", crop)[1].tobytes())
    return out


def render(video, path, results, out_path):
    """Annotated copy of the clip: the followed dancers boxed, each line shown in its clean space."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    silent = out_path.with_suffix(".silent.mp4")
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    times = np.array(sorted(path))
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        if len(times):
            nearest = times[np.abs(times - t).argmin()]
            if abs(nearest - t) < 0.15:
                for box, _, _ in path[nearest]:
                    cv2.rectangle(frame, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (230, 160, 255), 2)
        for r in results:
            space = r["clean_space"]
            if r["line"] and space and space[0] <= t < space[1] + 1.0:
                cv2.rectangle(frame, (0, h - 40), (w, h), (0, 0, 0), -1)
                cv2.putText(frame, r["line"], (8, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        writer.write(frame)
        i += 1
    writer.release()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", video,
                    "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(out_path)],
                   check=True)
    silent.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("clip")
    parser.add_argument("--beats-per-bar", type=int, default=4)
    parser.add_argument("--bars-per-phrase", type=int, default=4)
    parser.add_argument("--no-frames", action="store_true", help="features only, no close-up crops")
    args = parser.parse_args()

    song = map_song(load_audio(args.clip), beats_per_bar=args.beats_per_bar,
                    bars_per_phrase=args.bars_per_phrase, speech_seconds=2.5)
    print(f"music: {song['bpm']} bpm, {len(song['phrases'])} phrases")

    frames = detect(args.clip)
    path, solo, size = follow(frames)
    print(f"following {'one dancer' if solo else 'a couple'} in {len(path)}/{len(frames)} sampled frames")

    results, previous = [], []
    for n, ((start, end), space) in enumerate(zip(song["phrases"], song["clean_spaces"])):
        features = phrase_features(path, size, solo, start, end, n)
        shots = [] if args.no_frames or features["tracking"] == "poor" else crops(args.clip, path, start, end)
        result = describe(features, previous, frames=shots)
        if result.line:
            previous.append(result.line)
        results.append({"features": features, "line": result.line, "attempts": result.attempts, "clean_space": space})
        print(f"\nphrase {n} ({start:.1f}-{end:.1f}s) tracking={features['tracking']} events={features.get('events')}")
        for a in result.attempts:
            if not a["passed"]:
                print(f"   rejected: \"{a['draft']}\" ({a['reason']})")
        print(f"   -> {result.line or '(silent)'}" + (f"  [spoken at {space[0]:.1f}s]" if result.line and space else ""))

    out_dir = ROOT / "data/killtest"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.clip).stem
    (out_dir / f"{stem}.json").write_text(json.dumps(results, indent=2, default=float))
    render(args.clip, path, results, out_dir / f"{stem}-annotated.mp4")
    print(f"\nannotated video: {out_dir / f'{stem}-annotated.mp4'}")


if __name__ == "__main__":
    main()
