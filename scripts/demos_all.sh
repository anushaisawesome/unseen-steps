#!/bin/sh
# Every YouTube demo at once, each in its own process (6 at a time); the page updates as each one finishes.
# Usage: scripts/demos_all.sh [key ...]   (no keys: all of them)
cd "$(dirname "$0")/.." || exit 1
KEYS="${*:-$(.venv/bin/python -c 'import sys; sys.path.insert(0, "scripts"); import youtube_demo as y; print(" ".join(v[0] for v in y.VIDEOS))')}"
for k in $KEYS; do echo "$k"; done | xargs -P 6 -I{} sh -c '.venv/bin/python -u scripts/youtube_demo.py --part {} && .venv/bin/python scripts/youtube_demo.py --merge'
