"""Contact sheet of who the follower picks: grey = everyone detected, pink = followed.

Usage:
    python scripts/track_debug.py clips/waltz.mp4 out.jpg [--seed t,x,y]
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from killtest import detect, follow  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("clip")
parser.add_argument("out")
parser.add_argument("--seed")
args = parser.parse_args()

frames, frame_size = detect(args.clip)
seed = tuple(float(x) for x in args.seed.split(",")) if args.seed else None
path, solo, _ = follow(frames, frame_size, seed)
print(f"followed in {len(path)}/{len(frames)} frames, {'solo' if solo else 'couple'}")

cap = cv2.VideoCapture(args.clip)
duration = frames[-1][0]
tiles = []
for T in np.linspace(1, duration - 0.5, 12):
    cap.set(cv2.CAP_PROP_POS_MSEC, T * 1000)
    ok, img = cap.read()
    t, people = min(frames, key=lambda f: abs(f[0] - T))
    for box, *_ in people:
        cv2.rectangle(img, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (160, 160, 160), 2)
    for box, *_ in path.get(round(t, 3), []):
        cv2.rectangle(img, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (230, 80, 255), 5)
    cv2.putText(img, f"{T:.0f}s", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 255, 255), 4)
    tiles.append(cv2.resize(img, (426, 240)))
cv2.imwrite(args.out, cv2.vconcat([cv2.hconcat(tiles[i:i + 3]) for i in range(0, 12, 3)]))
