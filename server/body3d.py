"""3D body measurements from SAM-Body4D, for the upload path.

The YOLO features in scripts/killtest.py are 2D: turns are guessed from shoulders swapping sides on screen,
and a leg in front of the body looks the same as one behind it. SAM-Body4D gives 70 named 3D joints per frame
(scripts/sam_body4d/, saved as *_kp3d.npy in its results zip), so here we measure in the dancer's own frame:
how far she rotates and which way, when both feet leave the floor, heels lifted (relevé), bent knees (plié),
and leg shapes ballet names: arabesque, attitude, passé, développé.

Joints are in metres, OpenGL camera axes (y roughly up, camera looking down -z). Depth from a single camera
jitters frame to frame (~10 cm), so positions are smoothed and body-relative angles are preferred.

Usage:
    python server/body3d.py results.zip      # prints the measured timeline
"""

import re
import sys
import zipfile
from dataclasses import dataclass

import numpy as np

FPS = 24
NOSE, L_SHO, R_SHO, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK = 0, 5, 6, 9, 10, 11, 12, 13, 14
L_TOE, L_HEEL, R_TOE, R_HEEL = 15, 17, 18, 20
R_WRIST, L_WRIST, NECK = 41, 62, 69
LEGS = {"left": (L_HIP, L_KNEE, L_ANK, L_TOE, L_HEEL), "right": (R_HIP, R_KNEE, R_ANK, R_TOE, R_HEEL)}


def load(zip_path: str) -> np.ndarray:
    """(frames, 70, 3) joints from a SAM-Body4D results zip; frames with no body are NaN."""
    z = zipfile.ZipFile(zip_path)
    names = sorted(n for n in z.namelist() if n.endswith("_kp3d.npy"))
    if not names:
        raise SystemExit(f"{zip_path} has no *_kp3d.npy joints: rerun the notebook with the joint-saving patch")
    frames = [int(re.search(r"(\d+)_kp3d\.npy$", n).group(1)) for n in names]
    out = np.full((max(frames) + 1, 70, 3), np.nan)
    for f, n in zip(frames, names):
        with z.open(n) as fh:
            out[f] = np.load(fh)
    return out


def smooth(x: np.ndarray, k: int = 5) -> np.ndarray:
    """Centred moving median along time (axis 0), ignoring NaN frames."""
    out = np.copy(x)
    for i in range(len(x)):
        w = x[max(0, i - k // 2): i + k // 2 + 1]
        if np.isfinite(w).any():
            out[i] = np.nanmedian(w, axis=0)
    return out


def angle(a, b, c) -> np.ndarray:
    """Angle at b (degrees) between b->a and b->c, per frame."""
    u, v = a - b, c - b
    cos = (u * v).sum(-1) / (np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1) + 1e-9)
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


@dataclass
class Body:
    """Per-frame measurements for the whole clip."""
    up: np.ndarray            # (3,) floor normal
    height: dict              # joint name -> height above the floor (m), per frame
    yaw: np.ndarray           # facing angle in the floor plane, unwrapped (degrees; + = anticlockwise from above)
    facing: np.ndarray        # degrees between where she faces and the camera (0 = facing us, 180 = back to us)
    knee: dict                # side -> knee angle (180 = straight)
    leg_raise: dict           # side -> angle of hip->ankle from straight down (degrees)
    leg_dir: dict             # side -> "front" / "side" / "back" for a raised leg
    pelvis: np.ndarray        # (frames, 3) smoothed hip centre


def measure(kp: np.ndarray) -> Body:
    kp = smooth(kp, 3)
    ok = np.isfinite(kp[:, 0, 0])
    hips = (kp[:, L_HIP] + kp[:, R_HIP]) / 2

    # Floor: a plane through the lower envelope of the lowest foot point in each frame (two refits).
    feet = kp[:, [L_TOE, L_HEEL, R_TOE, R_HEEL, L_ANK, R_ANK]]
    torso = np.nanmedian(kp[ok, NECK] - hips[ok], axis=0)
    up = torso / np.linalg.norm(torso)
    low = feet[np.arange(len(kp)), np.nanargmin(np.where(np.isfinite(feet[..., 0]), feet @ up, np.inf), axis=1)]
    pts = low[ok]
    keep = np.ones(len(pts), bool)
    for _ in range(3):
        c = pts[keep].mean(0)
        normal = np.linalg.svd(pts[keep] - c)[2][-1]
        normal = normal if normal @ up > 0 else -normal
        d = (pts - c) @ normal
        keep = d < np.percentile(d, 60)  # feet on the floor are the lowest points; jumps and lifts sit above
    up, origin = normal, c - normal * np.percentile(((pts - c) @ normal)[keep], 20)

    def h(j):
        return (kp[:, j] - origin) @ up

    height = {name: h(j) for name, j in
              [("l_toe", L_TOE), ("l_heel", L_HEEL), ("r_toe", R_TOE), ("r_heel", R_HEEL), ("l_ank", L_ANK),
               ("r_ank", R_ANK), ("l_knee", L_KNEE), ("r_knee", R_KNEE), ("pelvis", None), ("neck", NECK),
               ("l_wrist", L_WRIST), ("r_wrist", R_WRIST)] if j is not None}
    height["pelvis"] = (hips - origin) @ up

    def flat(v):  # project onto the floor plane
        return v - np.outer(v @ up, up)

    left = flat(kp[:, L_HIP] - kp[:, R_HIP] + kp[:, L_SHO] - kp[:, R_SHO])
    forward = np.cross(left, up)
    forward /= np.linalg.norm(forward, axis=1, keepdims=True) + 1e-9
    # floor-plane axes: e1 toward the camera's right, e2 = up x e1
    e1 = flat(np.array([[1.0, 0, 0]]))[0]; e1 /= np.linalg.norm(e1)
    e2 = np.cross(up, e1)
    raw = np.degrees(np.arctan2(forward @ e2, forward @ e1))
    yaw = np.copy(raw)
    yaw[ok] = np.degrees(np.unwrap(np.radians(raw[ok])))
    to_cam = flat(-hips)
    to_cam /= np.linalg.norm(to_cam, axis=1, keepdims=True) + 1e-9
    facing = np.degrees(np.arccos(np.clip((forward * to_cam).sum(1), -1, 1)))

    knee, leg_raise, leg_dir = {}, {}, {}
    side_axis = left / (np.linalg.norm(left, axis=1, keepdims=True) + 1e-9)
    for side, (hp, kn, an, _, _) in LEGS.items():
        knee[side] = angle(kp[:, hp], kp[:, kn], kp[:, an])
        leg = kp[:, an] - kp[:, hp]
        leg_raise[side] = np.degrees(np.arccos(np.clip(-(leg @ up) / (np.linalg.norm(leg, axis=1) + 1e-9), -1, 1)))
        fl = flat(leg)
        fwd, lat = (fl * forward).sum(1), np.abs((fl * side_axis).sum(1))
        leg_dir[side] = np.where(lat > np.abs(fwd), "side", np.where(fwd > 0, "front", "back"))
    return Body(up, height, yaw, facing, knee, leg_raise, leg_dir, smooth(hips, 9))


def runs(mask: np.ndarray, min_frames: int):
    """(start, end) frame spans where mask holds for at least min_frames."""
    out, start = [], None
    for i, m in enumerate(list(mask) + [False]):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start >= min_frames:
                out.append((start, i))
            start = None
    return out


def events(b: Body) -> list[dict]:
    """The measured timeline: jumps, turns, leg shapes, relevé, plié, facing."""
    H, n, ev = b.height, len(b.yaw), []
    lowest = np.nanmin(np.stack([H["l_toe"], H["l_heel"], H["r_toe"], H["r_heel"]]), axis=0)
    for s, e in runs(lowest > 0.10, 3):  # the model often puts a planted pointe foot ~5-10 cm up
        ev.append({"kind": "jump", "start": s, "end": e, "detail": f"both feet off the floor, up to {np.nanmax(lowest[s:e]) * 100:.0f} cm"})

    # Turns: spans rotating faster than 180 degrees/s, kept if they add up to at least 150 degrees.
    rate = np.gradient(np.nan_to_num(b.yaw)) * FPS  # deg/s, + = anticlockwise seen from above
    spinning = np.abs(smooth(rate[:, None], 5)[:, 0]) > 180
    for s, e in runs(spinning, 4):
        deg = b.yaw[e - 1] - b.yaw[s]
        if abs(deg) >= 150:
            way = "left" if deg > 0 else "right"  # anticlockwise from above = turning to her left
            ev.append({"kind": "turn", "start": s, "end": e, "degrees": round(float(deg)),
                       "detail": f"turns {abs(deg):.0f} degrees to her {way}"})

    for side, other in (("left", "right"), ("right", "left")):
        k = side[0]
        standing = (np.minimum(H[f"{other[0]}_toe"], H[f"{other[0]}_heel"]) < 0.12)
        raised = b.leg_raise[side]
        shapes = {
            "arabesque": standing & (raised > 40) & (b.leg_dir[side] == "back") & (b.knee[side] > 150),
            "attitude": standing & (raised > 35) & (b.leg_dir[side] == "back") & (b.knee[side] < 140) & (b.knee[side] > 60),
            "développé": standing & (raised > 45) & (b.leg_dir[side] != "back") & (b.knee[side] > 150),
            "passé": standing & (b.knee[side] < 100) & (np.abs(H[f"{k}_ank"] - H[f"{other[0]}_knee"]) < 0.15),
        }
        for name, mask in shapes.items():
            for s, e in runs(mask, 4):
                ev.append({"kind": name, "start": s, "end": e, "leg": side,
                           "detail": f"{side} leg {('raised ' + str(round(float(np.nanmax(raised[s:e])))) + ' degrees ') if name != 'passé' else ''}"
                                     f"{b.leg_dir[side][s + (e - s) // 2] if name != 'passé' else 'foot at the other knee'}"
                                     f", knee {np.nanmedian(b.knee[side][s:e]):.0f} degrees"})

    heel_up = lambda k: (H[f"{k}_heel"] - H[f"{k}_toe"] > 0.07) & (H[f"{k}_toe"] < 0.08)
    for s, e in runs(heel_up("l") | heel_up("r"), 6):
        ev.append({"kind": "relevé", "start": s, "end": e, "detail": "heels lifted, on the balls of the feet or pointe"})
    grounded = (np.minimum(H["l_toe"], H["l_heel"]) < 0.08) & (np.minimum(H["r_toe"], H["r_heel"]) < 0.08)
    for s, e in runs(grounded & (b.knee["left"] < 145) & (b.knee["right"] < 145), 5):
        ev.append({"kind": "plié", "start": s, "end": e,
                   "detail": f"both knees bent to {np.nanmin(np.maximum(b.knee['left'][s:e], b.knee['right'][s:e])):.0f} degrees"})
    arms_up = (H["l_wrist"] > H["neck"] + 0.15) & (H["r_wrist"] > H["neck"] + 0.15)
    for s, e in runs(arms_up, 6):
        ev.append({"kind": "arms overhead", "start": s, "end": e, "detail": "both hands above the head"})
    return sorted(ev, key=lambda e: e["start"])


def facing_word(deg: float) -> str:
    return "facing us" if deg < 35 else "on a diagonal toward us" if deg < 70 else "side-on" if deg < 115 \
        else "on a diagonal away" if deg < 150 else "back to us"


def features(b: Body, ev: list[dict], start_s: float, end_s: float) -> dict:
    """3D features for one moment, plus overrides of the 2D keys the checker already uses."""
    s, e = max(0, int(start_s * FPS)), min(len(b.yaw), int(np.ceil(end_s * FPS)) + 1)
    if e - s < 2 or not np.isfinite(b.yaw[s:e]).any():
        return {"body3d": False}
    inside = [x for x in ev if x["start"] < e and x["end"] > s]
    kinds = {x["kind"] for x in inside}
    turns = [x for x in inside if x["kind"] == "turn"]
    deg = sum(x["degrees"] for x in turns)
    rotation = None if not turns else "left" if deg > 0 else "right"
    yaw = b.yaw[s:e][np.isfinite(b.yaw[s:e])]
    net = float(yaw[-1] - yaw[0]) if len(yaw) > 1 else 0.0
    pelvis = b.height["pelvis"][s:e]
    stand = np.nanpercentile(b.height["pelvis"], 75)
    drop = float(stand - np.nanmin(pelvis))
    f = {
        "body3d": True,
        "turn_degrees": round(abs(deg)),
        "rotation_3d": rotation,
        "net_rotation": round(net),
        "jump_3d": "jump" in kinds,
        "shapes_3d": sorted(kinds & {"arabesque", "attitude", "développé", "passé", "relevé", "plié", "arms overhead"}),
        "facing_3d": facing_word(float(np.nanmedian(b.facing[s:e]))),
        "hip_drop_m": round(drop, 2),
        "timeline_3d": [f"{x['start'] / FPS:.1f}-{x['end'] / FPS:.1f}s {x['kind']}: {x['detail']}" for x in inside],
    }
    # Overrides for checker.py's existing rules: 3D replaces the 2D guesses for jumps, turns and level.
    f["max_rise"] = None  # jumps are checked by the 3D rule below instead
    f["turns"] = round(abs(deg) / 360) or (1 if turns or abs(net) >= 90 else 0)
    f["rotation"] = rotation
    f["lowest_level"] = "floor" if np.nanmin(pelvis) < 0.45 else "low" if drop > 0.12 or "plié" in kinds else "standing"
    return f


# word stems -> (what the 3D features must show, reason if they don't). Applied only when body3d is True.
CLAIMS_3D = [
    (r"\b(jump|leap|hop|spring|bound|soar|vault)\w*|\b(jet[eé]s?|sissonnes?|soubresauts?|entrechats?|cabrioles?|"
     r"assembl[eé]s?|saut[eé]s?|changements?|tour en l'air|in the air|mid-air|airborne)\b",
     lambda f: f["jump_3d"], "it mentions a jump, but both feet never left the floor in 3D"),
    (r"\b(pirouett\w*|fouett\w*|ch[aâ]+n[eé]s?|spins?|spinning)\b",
     lambda f: f["turn_degrees"] >= 300, "it names a full turn, but the 3D body rotated less than 300 degrees"),
    (r"\b(double|two)\s+(pirouett|turn|spin)\w*",
     lambda f: f["turn_degrees"] >= 660, "it says a double turn, but the 3D body rotated less than 660 degrees"),
    (r"\barabesques?\b", lambda f: "arabesque" in f["shapes_3d"],
     "it says arabesque, but no leg was measured raised straight behind"),
    (r"\battitudes?\b", lambda f: "attitude" in f["shapes_3d"],
     "it says attitude, but no bent leg was measured raised behind"),
    (r"\b(passé|passe|retir[eé])\b", lambda f: "passé" in f["shapes_3d"],
     "it says passé, but no foot was measured at the other knee"),
    (r"\b(d[eé]velopp[eé]s?|extends? (her|his|a|one) leg|leg (extends|unfolds)|battements?|kicks?)\b",
     lambda f: f["shapes_3d"] and {"développé", "arabesque", "attitude"} & set(f["shapes_3d"]),
     "it describes a raised leg, but no leg was measured above 45 degrees"),
    (r"\b(relev[eé]|pointe|tiptoes?|balls of (her|his) feet|rises? (up )?onto)\b",
     lambda f: "relevé" in f["shapes_3d"], "it says relevé or pointe, but the heels weren't measured lifted"),
    (r"\b(pli[eé]s?|bends? (her|his|both) knees|deep bend)\b",
     lambda f: "plié" in f["shapes_3d"] or f["hip_drop_m"] > 0.12, "it says plié, but the knees weren't measured bent"),
]


def check_3d(line: str, f: dict) -> str | None:
    """Reason the line contradicts the 3D measurements, or None."""
    if not f.get("body3d"):
        return None
    text = line.lower()
    for pattern, supported, reason in CLAIMS_3D:
        if re.search(pattern, text) and not supported(f):
            return reason
    return None


def timeline(ev: list[dict]) -> str:
    """The measured timeline as notes for Argon."""
    return "\n".join(f"- {x['start'] / FPS:.1f}-{x['end'] / FPS:.1f} s {x['kind']}: {x['detail']}" for x in ev)


if __name__ == "__main__":
    b = measure(load(sys.argv[1]))
    ev = events(b)
    print(f"floor normal {np.round(b.up, 2)}, {len(ev)} events")
    print(timeline(ev))
