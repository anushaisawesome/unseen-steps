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
from speech import speak  # noqa: E402
from localise import localise  # noqa: E402
import wave  # noqa: E402

def pick_device():
    """NVIDIA GPU on Windows/Linux, Apple GPU on a Mac, otherwise the CPU."""
    import torch
    if torch.cuda.is_available():
        return 0
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


DEVICE = pick_device()


def load_pose(name):
    """A pose model from models/, downloaded by Ultralytics on first use if it isn't there yet."""
    path = ROOT / "models" / name
    return YOLO(str(path) if path.exists() else name)


# COCO keypoints
NOSE, L_SHO, R_SHO, L_WRI, R_WRI, L_HIP, R_HIP, L_KNE, R_KNE, L_ANK, R_ANK = 0, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16
SAMPLE_FPS = 15
TURN_HOLD = 0.3   # seconds a new facing must last to count as a turn
APART_GAP = 0.8   # hip distance between partners, in body heights
APART_HOLD = 1.0  # seconds a separation (or rejoining) must last to count
MOVING = 0.012    # activity below this (body heights per sampled frame, camera removed) means standing still


def appearance(frame, box, xy, conf):
    """Colour fingerprint of someone's clothes: an HSV histogram of the torso and legs."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    top = y0 + 0.2 * h
    if conf[L_SHO] > 0.3 and conf[R_SHO] > 0.3:
        top = max(y0, min(xy[L_SHO][1], xy[R_SHO][1]))
    region = frame[int(top):int(y1 - 0.08 * h), int(x0 + 0.2 * w):int(x1 - 0.2 * w)]
    if region.size == 0:
        return None
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [18, 4, 4], [0, 180, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    return hist, float(hsv[..., 1].mean())


def seated(box, xy, conf):
    """Spectators are mostly sitting: thighs close to horizontal."""
    h = box[3] - box[1]
    if min(conf[L_HIP], conf[R_HIP], conf[L_KNE], conf[R_KNE]) < 0.3:
        return False
    thigh = ((xy[L_KNE][1] + xy[R_KNE][1]) - (xy[L_HIP][1] + xy[R_HIP][1])) / 2
    return thigh < 0.12 * h


def detect(video: str):
    """Every sampled frame: (t, [(box, keypoints xy, keypoint conf, (colour hist, saturation), activity), ...]).

    Activity is how much a person moves relative to the crowd as a whole, so a panning camera
    doesn't make standing spectators look like they're dancing.
    """
    model = load_pose("yolo11n-pose.pt")
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    step = max(1, round(fps / SAMPLE_FPS))
    frames, i = [], 0
    last_seen, activity = {}, {}
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            r = model.track(frame, imgsz=1280, conf=0.2, persist=True, verbose=False, device=DEVICE,
                            tracker="bytetrack.yaml")[0]
            ids = r.boxes.id.int().tolist() if r.boxes.id is not None else [None] * len(r.boxes)
            rows = list(zip(ids, r.boxes.xyxy.cpu().numpy(), r.keypoints.xy.cpu().numpy(), r.keypoints.conf.cpu().numpy()))
            moves = {tid: centre(box) - last_seen[tid] for tid, box, _, _ in rows if tid in last_seen}
            # Camera pan = how the crowd moves as a whole; with fewer than 3 people there's no crowd to measure.
            camera = np.median(list(moves.values()), axis=0) if len(moves) >= 3 else np.zeros(2)
            people = []
            for tid, box, xy, conf in rows:
                own = np.linalg.norm(moves[tid] - camera) / height(box) if tid in moves else 0.0
                activity[tid] = 0.85 * activity.get(tid, own) + 0.15 * own
                if tid is not None:
                    last_seen[tid] = centre(box)
                look = appearance(frame, box, xy, conf)
                if look is not None and not seated(box, xy, conf):
                    people.append((box, xy, conf, look, activity[tid]))
            frames.append((i / fps, people))
        i += 1
    return frames, size


def centre(box):
    return np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])


def height(box):
    return box[3] - box[1]


def colour_distance(a, b):
    return cv2.compareHist(a, b, cv2.HISTCMP_BHATTACHARYYA)  # 0 = same colours, 1 = nothing alike


def pick_seed(frames, frame_size, seed=None):
    """The couple to follow: the one nearest a given point, or the most central pair in view."""
    mid = np.array(frame_size) / 2
    diag = np.linalg.norm(frame_size)
    if seed:  # (time in seconds, x and y as fractions of the frame)
        t0, fx, fy = seed
        t, people = min(frames, key=lambda f: abs(f[0] - t0))
        target = np.array([fx * frame_size[0], fy * frame_size[1]])
        first = min(people, key=lambda p: np.linalg.norm(centre(p[0]) - target))
        others = [p for p in people if p is not first and np.linalg.norm(centre(p[0]) - centre(first[0])) < height(first[0])]
        partner = min(others, key=lambda p: np.linalg.norm(centre(p[0]) - centre(first[0]))) if others else None
        return t, first, partner
    best = None
    for t, people in frames:
        for a in range(len(people)):
            for b in range(a + 1, len(people)):
                pa, pb = people[a], people[b]
                if np.linalg.norm(centre(pa[0]) - centre(pb[0])) < 0.8 * height(pa[0]) and height(pa[0]) > 0.15 * frame_size[1]:
                    centrality = 1 - np.linalg.norm((centre(pa[0]) + centre(pb[0])) / 2 - mid) / diag
                    if min(pa[4], pb[4]) < MOVING:
                        continue
                    score = centrality + 0.3 * (pa[2].mean() + pb[2].mean()) / 2 + 3 * min(pa[4], pb[4])
                    if best is None or score > best[0]:
                        best = (score, t, pa, pb)
    if best is None:
        return None
    _, t, pa, pb = best
    return t, pa, pb


def follow(frames, frame_size, seed=None):
    """Follow one dancer (and their partner) by the colour of their clothes, with position as a tiebreak.

    The more colourful partner (usually the dress) is followed directly; the other partner is
    whoever close by best matches their clothes.
    """
    picked = pick_seed(frames, frame_size, seed)
    if picked is None:  # no couple anywhere: follow the clearest moving person on their own
        candidates = [(t, p) for t, people in frames for p in people if p[4] >= MOVING]
        if not candidates:
            return {}, True, 0
        seed_t, best = max(candidates, key=lambda c: c[1][2].mean() + c[1][4])
        picked = (seed_t, best, None)
    seed_t, a, b = picked
    primary, partner = (a, b) if b is None or a[3][1] >= b[3][1] else (b, a)
    solo = partner is None

    if solo:
        # One dancer: follow the biggest, clearest person in each frame. Clothing colour is unreliable
        # for plain or dark clothes in changing light, and reflections in windows are much smaller.
        path = {}
        typical = height(primary[0])
        for t, people in frames:
            big = [p for p in people if height(p[0]) > 0.5 * typical]
            if big:
                best = max(big, key=lambda p: height(p[0]) * p[2].mean())
                path[round(t, 3)] = [best]
                typical = 0.9 * typical + 0.1 * height(best[0])
        sizes = [height(people[0][0]) for people in path.values()]
        return path, True, float(np.median(sizes)) if sizes else 0.0

    path = {}
    for direction in (1, -1):  # grow outwards from the seed, forwards then backwards
        ref = primary[3][0].copy()
        pos, h, lost_since = centre(primary[0]), height(primary[0]), None
        partner_pos = centre(partner[0]) if partner is not None else None
        for t, people in sorted([f for f in frames if (f[0] - seed_t) * direction >= 0], key=lambda f: direction * f[0]):
            lost = lost_since is not None and abs(t - lost_since) > 1.5
            best, best_cost = None, None
            for p in people:
                look = colour_distance(ref, p[3][0])
                dist = np.linalg.norm(centre(p[0]) - pos) / max(h, height(p[0]))
                # The "is this person moving" filter is for ignoring spectators in a crowd; a soloist
                # standing still for a moment is still the dancer.
                still = p[4] < (2 * MOVING if lost else MOVING) and len(people) > 1
                if still or look > (0.35 if lost else 0.6) or (dist > 2.5 and not lost):
                    continue
                cost = look + 0.3 * min(dist, 3)
                if best_cost is None or cost < best_cost:
                    best, best_cost = p, cost
            if best is None:
                lost_since = lost_since if lost_since is not None else t
                continue
            lost_since = None
            chosen = [best]
            if not solo:
                near = [p for p in people if p is not best and p[4] >= MOVING
                        and np.linalg.norm(centre(p[0]) - centre(best[0])) < 0.8 * height(best[0])
                        and abs(height(p[0]) - height(best[0])) < 0.35 * height(best[0])
                        and colour_distance(partner[3][0], p[3][0]) < 0.6]
                if near:
                    # Prefer whoever is where the partner just was, so a passer-by can't take over.
                    def partner_cost(p):
                        jump = np.linalg.norm(centre(p[0]) - partner_pos) / height(best[0]) if partner_pos is not None else 0
                        return colour_distance(partner[3][0], p[3][0]) + 0.5 * min(jump, 2)
                    mate = min(near, key=partner_cost)
                    chosen.append(mate)
                    partner_pos = centre(mate[0])
            path[round(t, 3)] = chosen
            pos, h = centre(best[0]), height(best[0])
            if colour_distance(ref, best[3][0]) < 0.4:
                ref = 0.9 * ref + 0.1 * best[3][0]
    sizes = [height(people[0][0]) for people in path.values()]
    return path, solo, float(np.median(sizes)) if sizes else 0.0


def dress_histogram(frame, box):
    """Hue-saturation fingerprint of the clothes in the middle of a box (the dress, for her)."""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    region = frame[y0 + int(0.25 * h):y1 - int(0.1 * h), x0 + int(0.25 * w):x1 - int(0.25 * w)]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 60, 40), (180, 255, 255))
    hist = cv2.calcHist([hsv], [0, 1], mask, [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 255, cv2.NORM_MINMAX)
    return hist


def smooth_points(prev, xy, conf, body):
    """Steady the skeleton: blend with the last frame and cap any single-frame jump, so one bad
    detection can't throw a limb across the picture."""
    if prev is None:
        return xy
    out = xy.copy()
    for k in range(len(xy)):
        if conf[k] < 0.3:
            out[k] = prev[k]
            continue
        step = xy[k] - prev[k]
        dist = np.linalg.norm(step)
        if dist > 0.35 * body:
            step = step / dist * 0.35 * body
        out[k] = prev[k] + 0.7 * step
    return out


def track_focus(video, seed, model_name="yolo11n-pose.pt"):
    """Follow one couple through a crowd the way a person would.

    Her dress colour is followed with CamShift, searching only near where it was last seen. A steady
    frame glides around the couple, and pose runs only inside that frame (enlarged), so everyone
    else is ignored. Skeletons are smoothed over time. Starts at the seed time.
    """
    model = load_pose(model_name)
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    step = max(1, round(fps / SAMPLE_FPS))
    t0, fx, fy = seed
    cap.set(cv2.CAP_PROP_POS_MSEC, t0 * 1000)
    i = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    ok, frame = cap.read()
    r = model.predict(frame, imgsz=1280, conf=0.25, verbose=False, device=DEVICE)[0]
    people = list(zip(r.boxes.xyxy.cpu().numpy(), r.keypoints.xy.cpu().numpy(), r.keypoints.conf.cpu().numpy()))
    point = np.array([fx * W, fy * H])
    first = min(people, key=lambda p: np.linalg.norm(centre(p[0]) - point))
    body = height(first[0])
    others = [p for p in people if p is not first and np.linalg.norm(centre(p[0]) - centre(first[0])) < body]
    second = min(others, key=lambda p: np.linalg.norm(centre(p[0]) - centre(first[0]))) if others else None
    dress = dress_histogram(frame, first[0])
    first_look = appearance(frame, first[0], first[1], first[2])[0]
    second_look = appearance(frame, second[0], second[1], second[2])[0] if second is not None else None
    solo = second is None

    window = tuple(int(v) for v in (first[0][0], first[0][1], first[0][2] - first[0][0], first[0][3] - first[0][1]))
    roi = None
    prev = {0: None, 1: None}
    partner_pos = centre(second[0]) if second is not None else None
    frames, path, focus = [], {}, {}
    term = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 1)
    while ok:
        if i % step == 0:
            t = round(i / fps, 3)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            back = cv2.calcBackProject([hsv], [0, 1], dress, [0, 180, 0, 256], 1)
            back &= cv2.inRange(hsv, (0, 60, 40), (180, 255, 255))
            # Search only near where the dress was last seen.
            x, y, w, h = window
            keep = np.zeros_like(back)
            keep[max(0, y - h):min(H, y + 2 * h), max(0, x - 2 * w):min(W, x + 3 * w)] = 1
            box, new_window = cv2.CamShift(back * keep, window, term)
            if new_window[2] > 4 and new_window[3] > 4:
                window = new_window
            dress_at = np.array(box[0])
            wx, wy, ww, wh = window
            strength = back[wy:wy + wh, wx:wx + ww].mean() if ww > 0 and wh > 0 else 0
            visible = strength > 40 and ww * wh > 0.02 * body * body
            if not visible:
                # Lost: look for her dress anywhere in the frame, a patch about her size.
                blur = cv2.GaussianBlur(back, (0, 0), max(2, body / 15))
                _, blobs = cv2.threshold(blur, 60, 255, cv2.THRESH_BINARY)
                n, labels, stats, cents = cv2.connectedComponentsWithStats(blobs.astype(np.uint8))
                best = None
                for k in range(1, n):
                    area = stats[k, cv2.CC_STAT_AREA]
                    on_floor = cents[k][1] > 0.45 * H  # the audience sits in the upper part of the picture
                    if on_floor and 0.03 * body * body < area < 0.6 * body * body and (best is None or area > stats[best, cv2.CC_STAT_AREA]):
                        best = k
                if best is not None:
                    # Confirm with pose: a standing person there whose clothes match hers.
                    cx, cy = cents[best]
                    r = model.predict(frame, imgsz=1280, conf=0.3, verbose=False, device=DEVICE)[0]
                    match = [b for b, xy, conf in zip(r.boxes.xyxy.cpu().numpy(), r.keypoints.xy.cpu().numpy(), r.keypoints.conf.cpu().numpy())
                             if b[0] <= cx <= b[2] and b[1] <= cy <= b[3] and not seated(b, xy, conf)
                             and (look := appearance(frame, b, xy, conf)) is not None and colour_distance(first_look, look[0]) < 0.45]
                    if not match:
                        best = None
                if best is not None:
                    bx, by, bw, bh = stats[best, :4]
                    window = (int(bx), int(by), int(max(bw, 5)), int(max(bh, 5)))
                    dress_at = np.array(cents[best])
                    roi = None  # jump straight to her rather than gliding across the floor
                    visible = True
            if not visible:
                prev = {0: None, 1: None}
                frames.append((t, []))
                ok, frame = cap.read()
                i += 1
                continue

            # Steady focus frame around the couple, gliding rather than jumping.
            target = np.array([dress_at[0] - 1.3 * body, dress_at[1] - 0.75 * body,
                               dress_at[0] + 1.3 * body, dress_at[1] + 0.75 * body])
            roi = target if roi is None else 0.75 * roi + 0.25 * target
            x0, y0 = int(max(0, roi[0])), int(max(0, roi[1]))
            x1, y1 = int(min(W, roi[2])), int(min(H, roi[3]))
            focus[t] = (x0, y0, x1, y1)

            chosen = []
            if x1 - x0 > 20 and y1 - y0 > 20:
                r = model.predict(frame[y0:y1, x0:x1], imgsz=640, conf=0.3, verbose=False, device=DEVICE)[0]
                found = []
                for b, xy, conf in zip(r.boxes.xyxy.cpu().numpy(), r.keypoints.xy.cpu().numpy(), r.keypoints.conf.cpu().numpy()):
                    b = b + np.array([x0, y0, x0, y0]); xy = xy + np.array([x0, y0])
                    look = appearance(frame, b, xy, conf)
                    if look is not None:
                        found.append((b, xy, conf, look, 1.0))
                if found:
                    # Her: the person standing where the dress is, and looking like her.
                    main = min(found, key=lambda p: np.linalg.norm(centre(p[0]) - dress_at) / body
                               + colour_distance(first_look, p[3][0]))
                    chosen.append(main)
                    if not solo:
                        rest = [p for p in found if p is not main
                                and np.linalg.norm(centre(p[0]) - centre(main[0])) < 0.6 * body
                                and colour_distance(second_look, p[3][0]) < 0.6]
                        if rest:
                            mate = min(rest, key=lambda p: colour_distance(second_look, p[3][0])
                                       + 0.5 * min(np.linalg.norm(centre(p[0]) - partner_pos) / body, 2))
                            chosen.append(mate)
                            partner_pos = centre(mate[0])
                    body = 0.9 * body + 0.1 * height(main[0])
            steady = []
            for role, p in enumerate(chosen):
                xy = smooth_points(prev[role], p[1], p[2], body)
                prev[role] = xy
                steady.append((p[0], xy, p[2], p[3], p[4]))
            if steady:
                path[t] = steady
            frames.append((t, []))
        ok, frame = cap.read()
        i += 1
    sizes = [height(people[0][0]) for people in path.values()]
    return frames, path, solo, float(np.median(sizes)) if sizes else 0.0, focus


def phrase_features(path, size, solo, start, end, phrase):
    rows = [(t, people) for t, people in sorted(path.items()) if start <= t < end]
    expected = (end - start) * SAMPLE_FPS
    base = {"phrase": phrase, "start": round(start, 1), "end": round(end, 1), "people": 1 if solo else 2}
    if len(rows) < 0.3 * expected:
        return {**base, "tracking": "poor"}

    t = np.array([r[0] for r in rows])
    lead = [r[1][0] for r in rows]
    size = float(np.median([p[0][3] - p[0][1] for p in lead]))
    hips = np.array([(p[1][L_HIP] + p[1][R_HIP]) / 2 for p in lead])
    centres = np.array([np.mean([(p[1][L_HIP] + p[1][R_HIP]) / 2 for p in people], axis=0) for _, people in rows])
    pairs = [people for _, people in rows if len(people) == 2]

    speed = np.linalg.norm(np.diff(centres, axis=0), axis=1) / size / np.maximum(np.diff(t), 1e-3)
    travel_x = (centres[-1, 0] - centres[0, 0]) / size
    travel = "left" if travel_x < -0.5 else "right" if travel_x > 0.5 else "none"
    rise = (np.median(hips[:, 1]) - hips[:, 1]) / size
    # Only trust leg length when the ankles are clearly visible (long dresses hide them).
    leg = np.array([(p[1][L_ANK][1] + p[1][R_ANK][1]) / 2 - (p[1][L_HIP][1] + p[1][R_HIP][1]) / 2
                    for p in lead if min(p[2][L_ANK], p[2][R_ANK]) > 0.5]) / size
    lowest = "standing" if len(leg) < 5 else "floor" if np.percentile(leg, 5) < 0.15 else "low" if np.percentile(leg, 5) < 0.3 else "standing"

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
        # A partner who isn't detected is usually hidden behind the followed dancer, so count
        # those frames as together rather than leaving gaps that look like a separation.
        def gap(people):
            if len(people) < 2:
                return 0.0
            a, b = people
            return float(np.linalg.norm((a[1][L_HIP] + a[1][R_HIP]) / 2 - (b[1][L_HIP] + b[1][R_HIP]) / 2) / size)
        pair_t = [tt for tt, _ in rows]
        gaps = [gap(people) for _, people in rows]
        separation = "in hold" if np.median(gaps) < 0.2 else "close" if np.median(gaps) < APART_GAP else "apart"
        # Only count a change of separation once it has clearly lasted APART_HOLD seconds.
        state, pending = gaps[0] > APART_GAP, None
        for tt, g in zip(pair_t, gaps):
            now = g > APART_GAP
            if now == state:
                pending = None
            elif pending is None:
                pending = tt
            elif tt - pending >= APART_HOLD:
                state, pending = now, None
                events.append((tt, "partners break apart" if now else "partners come back together"))

    if separation in ("in hold", "close"):
        # In a ballroom hold, raised arms are the hold itself, and long dresses hide the legs,
        # so arm, kick and low readings are unreliable.
        events = [e for e in events if e[1] not in ("arm raised high", "leg kick or high leg")]
        lowest = "standing"
    events = sorted(events)[:10]
    conf = np.mean([p[2].mean() for p in lead])
    coverage = len(rows) / expected
    tracking = "good" if conf > 0.5 and coverage > 0.7 else "ok" if conf > 0.35 and coverage > 0.4 else "poor"

    return {
        **base, "tracking": tracking,
        "speed": round(float(np.median(speed)), 2) if len(speed) else 0.0,
        "max_rise": round(float(np.percentile(rise, 95)), 2), "lowest_level": lowest, "travel": travel,
        "turns": turns,
        "arms_up": 0.0 if separation in ("in hold", "close") else
                   round(float(np.mean([min(p[1][L_WRI][1], p[1][R_WRI][1]) < p[1][NOSE][1] for p in lead])), 2),
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


SKELETON = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]
LEAD_COLOUR, PARTNER_COLOUR, OTHER_COLOUR = (230, 120, 255), (170, 235, 150), (150, 150, 150)  # BGR
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"


def draw_skeleton(frame, xy, conf, colour, thickness):
    for a, b in SKELETON:
        if conf[a] > 0.3 and conf[b] > 0.3:
            cv2.line(frame, tuple(int(v) for v in xy[a]), tuple(int(v) for v in xy[b]), colour, thickness, cv2.LINE_AA)
    for k in range(5, 17):
        if conf[k] > 0.3:
            cv2.circle(frame, tuple(int(v) for v in xy[k]), thickness + 1, colour, -1, cv2.LINE_AA)


def draw_text(frame, caption, note):
    """Caption bar at the bottom, a small title top left, and an optional checker note top right."""
    from PIL import Image, ImageDraw, ImageFont
    h, w = frame.shape[:2]
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    small = ImageFont.truetype(FONT, max(14, h // 40))
    d.text((int(0.02 * w), int(0.02 * h)), "Unseen Steps  ·  live audio description", font=small, fill=(255, 255, 255, 200))
    if caption:
        big = ImageFont.truetype(FONT, max(18, h // 20))
        tw = d.textlength(caption, font=big)
        pad, bh = int(0.02 * h), int(h / 20 * 1.9)
        x0, y0 = int((w - tw) / 2) - 2 * pad, h - bh - int(0.05 * h)
        d.rounded_rectangle((x0, y0, x0 + tw + 4 * pad, y0 + bh), radius=bh // 3, fill=(20, 16, 30, 190))
        d.text((x0 + 2 * pad, y0 + (bh - h // 20) // 2 - 2), caption, font=big, fill=(255, 255, 255, 255))
    if note:
        tw = d.textlength(note, font=small)
        top = int(0.065 * h)  # its own line, under the title
        d.rounded_rectangle((int(0.015 * w), top, int(0.035 * w) + tw, top + h // 40 + 14), radius=8, fill=(120, 20, 40, 190))
        d.text((int(0.025 * w), top + 5), note, font=small, fill=(255, 255, 255, 255))
    out = Image.alpha_composite(img, layer).convert("RGB")
    return cv2.cvtColor(np.array(out), cv2.COLOR_RGB2BGR)


def render(video, frames, path, results, out_path, focus=None):
    """Demo video: skeletons on the dancers (the followed couple highlighted), each line as a caption
    while it's spoken, any line the checker rejected flagged, and the spoken lines mixed into the music."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    silent = out_path.with_suffix(".silent.mp4")
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    times = np.array(sorted(path))
    sample_times = np.array([f[0] for f in frames])
    thick = max(2, h // 240)
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        followed = []
        if len(times):
            nearest = times[np.abs(times - t).argmin()]
            if abs(nearest - t) < 0.1:
                followed = path[nearest]
        k = int(np.abs(sample_times - t).argmin())
        if abs(sample_times[k] - t) < 0.1:
            ref_h = height(followed[0][0]) if followed else 0.25 * h
            for p in frames[k][1]:
                # Other dancers only: moving, standing on the floor (feet in the lower part of the
                # picture) and about the size of the followed dancer. Spectators at the edges get none.
                on_floor = p[0][3] > 0.55 * h and 0.6 * ref_h < height(p[0]) < 1.6 * ref_h
                if p[4] >= 2 * MOVING and on_floor and not any(p is q for q in followed):
                    draw_skeleton(frame, p[1], p[2], OTHER_COLOUR, 1)
        if focus and len(times):
            near = times[np.abs(times - t).argmin()]
            f = focus.get(near)
            if f and abs(near - t) < 0.15:
                cv2.rectangle(frame, (f[0], f[1]), (f[2], f[3]), (255, 255, 255), 1, cv2.LINE_AA)
        for n, p in enumerate(followed):
            draw_skeleton(frame, p[1], p[2], LEAD_COLOUR if n == 0 else PARTNER_COLOUR, thick)
        caption, note = None, None
        for r in results:
            said = r.get("speech")
            if said and said["at"] <= t < said["at"] + said["seconds"] + 0.5:
                caption = r["line"]
                rejected = [a for a in r["attempts"] if not a["passed"]]
                if rejected:
                    note = f'checker rejected "{rejected[0]["draft"]}": {rejected[0]["reason"]}'
        writer.write(draw_text(frame, caption, note))
        i += 1
    writer.release()
    # Mix each spoken line into the soundtrack at its clean space, with the music a little lower.
    said = [r["speech"] for r in results if r.get("speech")]
    inputs = ["-i", str(silent), "-i", video]
    graph = ["[1:a]volume=0.6[m]"]
    for k, sp in enumerate(said):
        inputs += ["-i", sp["path"]]
        graph.append(f"[{k + 2}:a]adelay=delays={int(sp['at'] * 1000)}:all=1,volume=1.8[n{k}]")
    graph.append("[m]" + "".join(f"[n{k}]" for k in range(len(said))) +
                 f"amix=inputs={len(said) + 1}:normalize=0:duration=first[a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(graph),
                    "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)],
                   check=True)
    silent.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("clip")
    parser.add_argument("--beats-per-bar", type=int, default=4)
    parser.add_argument("--bars-per-phrase", type=int, default=4)
    parser.add_argument("--no-frames", action="store_true", help="features only, no close-up crops")
    parser.add_argument("--model", default="yolo11n-pose.pt", help="pose model file in models/")
    parser.add_argument("--style", help="dance style for glossary terms, e.g. waltz")
    parser.add_argument("--terms", choices=["beginner", "professional"], default="beginner",
                        help="which names to speak (SPEC.md 5b); beginner falls back to plain description")
    parser.add_argument("--include-drafts", action="store_true", help="preview with unvetted glossary terms (never for the demo)")
    parser.add_argument("--lang", default="en", help="narration language: en, uk, de, hi")
    parser.add_argument("--seed", help="who to follow: time,x,y with x and y as fractions of the frame, e.g. 18,0.6,0.7")
    args = parser.parse_args()

    song = map_song(load_audio(args.clip), beats_per_bar=args.beats_per_bar,
                    bars_per_phrase=args.bars_per_phrase, speech_seconds=2.5, earliest=True)
    print(f"music: {song['bpm']} bpm, {len(song['phrases'])} phrases")

    seed = tuple(float(x) for x in args.seed.split(",")) if args.seed else None
    focus = None
    if seed:  # marked couple: follow her dress, pose only inside a steady frame around them
        frames, path, solo, size, focus = track_focus(args.clip, seed, args.model)
    else:
        frames, frame_size = detect(args.clip)
        path, solo, size = follow(frames, frame_size, seed)
    print(f"following {'one dancer' if solo else 'a couple'} in {len(path)}/{len(frames)} sampled frames")

    results, previous = [], []
    for n, ((start, end), space) in enumerate(zip(song["phrases"], song["clean_spaces"])):
        features = phrase_features(path, size, solo, start, end, n)
        shots = [] if args.no_frames or features["tracking"] == "poor" else crops(args.clip, path, start, end)
        vocab = []
        if args.style and features["tracking"] != "poor":
            from db import match_terms, spoken_name
            parts = [f"travels {features['travel']}" if features.get("travel") not in (None, "none") else "stays in place",
                     f"{features['turns']} turn(s)" if features.get("turns") else "no turns",
                     "pauses" if (features.get("stillness") or 0) > 0.3 else "keeps moving",
                     "rises" if (features.get("max_rise") or 0) > 0.05 else ""]
            movement = "; ".join([p for p in parts if p] + (features.get("events") or []))
            vocab = [f"{name} ({t['description']})" for t in
                     match_terms(movement, args.style, include_drafts=args.include_drafts)
                     if (name := spoken_name(t, args.terms))]
        if vocab:
            print(f"   terms offered: {[v.split(' (')[0] for v in vocab]}")
        result = describe(features, previous, vocab=vocab, frames=shots)
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
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    for n, r in enumerate(results):
        if r["line"] and r["clean_space"]:
            r["line_en"] = r["line"]
            r["line"] = localise(r["line"], args.lang)  # checked in English, then translated
            wav = speak(r["line"], audio_dir / f"{stem}-{args.lang}-{n}.wav")
            with wave.open(str(wav)) as f:
                seconds = f.getnframes() / f.getframerate()
            r["speech"] = {"path": str(wav), "at": r["clean_space"][0], "seconds": round(seconds, 2)}
    (out_dir / f"{stem}.json").write_text(json.dumps(results, indent=2, default=float))
    name = f"{stem}-annotated.mp4" if args.lang == "en" else f"{stem}-annotated-{args.lang}.mp4"
    render(args.clip, frames, path, results, out_dir / name, focus)
    print(f"\nannotated video: {out_dir / name}")


if __name__ == "__main__":
    main()
