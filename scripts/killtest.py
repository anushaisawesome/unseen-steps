"""Kill test: do real pose features give specific, correct lines?

Runs YOLO-pose with tracking over a clip, follows one couple (or a soloist), turns each
musical phrase into features, and runs the write-check loop on them. Also writes an
annotated video so the lines can be judged against what actually happened.

Usage:
    python scripts/killtest.py clips/clip1.mp4 [--beats-per-bar 4]
"""

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from music import load_audio, map_song  # noqa: E402
from narrate import describe  # noqa: E402

# COCO keypoints
NOSE, L_SHO, R_SHO, L_WRI, R_WRI, L_HIP, R_HIP, L_ANK, R_ANK = 0, 5, 6, 9, 10, 11, 12, 15, 16
SAMPLE_FPS = 10


def track_people(video: str):
    """Return {track_id: list of (t, box, keypoints xy, keypoint conf)} for the whole clip."""
    model = YOLO(str(ROOT / "models/yolo11n-pose.pt"))
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round(fps / SAMPLE_FPS))
    tracks = defaultdict(list)
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            r = model.track(frame, imgsz=1280, conf=0.25, persist=True, verbose=False,
                            device="mps", tracker="bytetrack.yaml")[0]
            if r.boxes.id is not None:
                for tid, box, xy, conf in zip(r.boxes.id.int().tolist(), r.boxes.xyxy.cpu().numpy(),
                                              r.keypoints.xy.cpu().numpy(), r.keypoints.conf.cpu().numpy()):
                    tracks[tid].append((i / fps, box, xy, conf))
        i += 1
    return tracks


def pick_couple(tracks):
    """The longest track, plus the track that stays closest to it (its partner), if any."""
    lead = max(tracks, key=lambda k: len(tracks[k]))
    lead_at = {round(t, 2): box for t, box, _, _ in tracks[lead]}
    best, best_dist = None, None
    for tid, frames in tracks.items():
        if tid == lead:
            continue
        dists = []
        for t, box, _, _ in frames:
            if round(t, 2) in lead_at:
                a, b = lead_at[round(t, 2)], box
                height = a[3] - a[1]
                dists.append(np.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2) / height)
        if len(dists) >= 0.5 * len(lead_at) and (best_dist is None or np.median(dists) < best_dist):
            best, best_dist = tid, float(np.median(dists))
    if best_dist is not None and best_dist < 1.0:
        return [lead, best]
    return [lead]


def phrase_features(tracks, ids, start, end, phrase):
    rows = {tid: [f for f in tracks[tid] if start <= f[0] < end] for tid in ids}
    lead = rows[ids[0]]
    if len(lead) < 5:
        return {"phrase": phrase, "start": start, "end": end, "people": len(ids), "tracking": "poor"}

    t = np.array([f[0] for f in lead])
    height = np.median([f[1][3] - f[1][1] for f in lead])
    hips = np.array([(f[2][L_HIP] + f[2][R_HIP]) / 2 for f in lead])
    ankles = np.array([(f[2][L_ANK] + f[2][R_ANK]) / 2 for f in lead])
    conf = np.array([f[3].mean() for f in lead])

    centre = hips
    if len(ids) == 2 and len(rows[ids[1]]) >= 5:
        partner = {round(f[0], 2): (f[2][L_HIP] + f[2][R_HIP]) / 2 for f in rows[ids[1]]}
        centre = np.array([(h + partner[round(tt, 2)]) / 2 if round(tt, 2) in partner else h
                           for tt, h in zip(t, hips)])
        gaps = [np.linalg.norm(h - partner[round(tt, 2)]) / height for tt, h in zip(t, hips) if round(tt, 2) in partner]
        both = len(gaps) / len(t)
        gap = float(np.median(gaps)) if gaps else None
        separation = None if gap is None else ("in hold" if gap < 0.35 else "close" if gap < 0.8 else "apart")
    else:
        both, separation = 1.0, None

    step = np.linalg.norm(np.diff(centre, axis=0), axis=1) / height
    dt = np.diff(t)
    speed = step / np.maximum(dt, 1e-3)
    travel_x = (centre[-1, 0] - centre[0, 0]) / height
    travel = "left" if travel_x < -0.5 else "right" if travel_x > 0.5 else "none"

    rise = (np.median(centre[:, 1]) - centre[:, 1]) / height  # image y grows downward
    leg = (ankles[:, 1] - hips[:, 1]) / height
    lowest = "floor" if leg.min() < 0.15 else "low" if leg.min() < 0.3 else "standing"

    facing = np.sign([f[2][L_SHO][0] - f[2][R_SHO][0] for f in lead])
    facing = facing[facing != 0]
    turns = int((np.abs(np.diff(facing)) > 0).sum() // 2) if len(facing) > 2 else 0

    arms_up = float(np.mean([min(f[2][L_WRI][1], f[2][R_WRI][1]) < f[2][NOSE][1] for f in lead]))
    stillness = float(np.mean(speed < 0.15)) if len(speed) else 0.0

    good = conf.mean() > 0.5 and both > 0.7
    tracking = "good" if good else "ok" if conf.mean() > 0.35 and both > 0.4 else "poor"

    features = {
        "phrase": phrase, "start": round(start, 1), "end": round(end, 1), "people": len(ids),
        "tracking": tracking, "speed": round(float(np.median(speed)), 2) if len(speed) else 0.0,
        "max_rise": round(float(np.percentile(rise, 95)), 2), "lowest_level": lowest,
        "travel": travel, "turns": turns, "arms_up": round(arms_up, 2),
        "stillness": round(stillness, 2), "separation": separation,
    }
    who = "the couple" if len(ids) == 2 else "the dancer"
    bits = [f"{who} travels {travel}" if travel != "none" else f"{who} stays in one area"]
    if turns:
        bits.append(f"{turns} turn{'s' if turns > 1 else ''}")
    if separation:
        bits.append(separation)
    if stillness > 0.3:
        bits.append("pauses")
    features["summary"] = ", ".join(bits)
    return features


def render(video, tracks, ids, results, out_path):
    """Annotated copy of the clip: the followed dancers boxed, each line shown in its clean space."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    silent = out_path.with_suffix(".silent.mp4")
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    boxes = {tid: {round(f[0], 1): f[1] for f in tracks[tid]} for tid in ids}
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        for tid in ids:
            box = boxes[tid].get(round(t, 1))
            if box is not None:
                cv2.rectangle(frame, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (230, 160, 255), 2)
        for r in results:
            space = r["clean_space"]
            if r["line"] and space and space[0] <= t < space[1] + 1.5:
                cv2.rectangle(frame, (0, h - 44), (w, h), (0, 0, 0), -1)
                cv2.putText(frame, r["line"], (10, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
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
    args = parser.parse_args()

    song = map_song(load_audio(args.clip), beats_per_bar=args.beats_per_bar)
    print(f"music: {song['bpm']} bpm, {len(song['phrases'])} phrases")

    tracks = track_people(args.clip)
    ids = pick_couple(tracks)
    print(f"tracked {len(tracks)} people; following {'a couple' if len(ids) == 2 else 'one dancer'} {ids}")

    results, previous = [], []
    for n, ((start, end), space) in enumerate(zip(song["phrases"], song["clean_spaces"])):
        features = phrase_features(tracks, ids, start, end, n)
        result = describe(features, previous)
        if result.line:
            previous.append(result.line)
        results.append({"features": features, "line": result.line, "attempts": result.attempts,
                        "clean_space": space})
        print(f"\nphrase {n} ({start:.1f}-{end:.1f}s): {json.dumps({k: features.get(k) for k in ('tracking', 'travel', 'turns', 'separation', 'max_rise', 'stillness')})}")
        for a in result.attempts:
            if not a["passed"]:
                print(f"   rejected: \"{a['draft']}\" ({a['reason']})")
        print(f"   -> {result.line or '(silent)'}" + (f"  [spoken at {space[0]:.1f}s]" if result.line and space else ""))

    out_dir = ROOT / "data/killtest"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.clip).stem
    (out_dir / f"{stem}.json").write_text(json.dumps(results, indent=2, default=float))
    render(args.clip, tracks, ids, results, out_dir / f"{stem}-annotated.mp4")
    print(f"\nannotated video: {out_dir / f'{stem}-annotated.mp4'}")


if __name__ == "__main__":
    main()
