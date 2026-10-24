#!/bin/sh
# Rebuild clips/ballet.mp4, the current demo clip (clips/ isn't in the repo).
# Video: Mixkit stock clip 956 "A young ballerina dancing in a white room" (free Mixkit licence).
# Music: librosa's example "Dance of the Sugar Plum Fairy", Kevin MacLeod (incompetech.com), CC BY: credit it.
set -e
cd "$(dirname "$0")/.."
mkdir -p clips
curl -sSfL -o clips/mix956.mp4 https://assets.mixkit.co/videos/956/956-720.mp4
python -c "import librosa, shutil; shutil.copy(librosa.example('nutcracker'), 'clips/nutcracker.ogg')"
ffmpeg -v error -y -i clips/mix956.mp4 -ss 16 -i clips/nutcracker.ogg -map 0:v -map 1:a -c:v copy -c:a aac -shortest clips/ballet.mp4
echo "clips/ballet.mp4 ready. Render it with: python scripts/killtest.py clips/ballet.mp4 --bars-per-phrase 2"
