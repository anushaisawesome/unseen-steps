"""Fill template.html with a SAM-Body4D run: python build_viewer.py <zip> <ballet-demo.mp4> <out.html>

The zip is what the Colab notebook downloads (anim.json, overlay.mp4, focal_4d_individual/).
Vertices go in as gzipped frame-to-frame uint16 deltas; both videos as data URIs.
"""
import base64, gzip, json, statistics, sys, zipfile
from pathlib import Path

import numpy as np

zip_path, demo_path, out_path = sys.argv[1:4]
HERE = Path(__file__).parent
TOTAL_FRAMES, HEIGHT = 547, 720  # Mixkit 956 at 24 fps, 1280x720 (checked against ballet-demo.mp4)

z = zipfile.ZipFile(zip_path)
anim = json.loads(z.read("anim.json"))
person = max(anim["people"], key=lambda p: len(p["frames"]))
n = person["vertexCount"]
q = np.frombuffer(base64.b64decode(person["vertices"]), dtype="<u2").reshape(-1, n * 3)
deltas = np.diff(q.astype(np.int64), axis=0, prepend=0).astype(np.uint16)  # wraps mod 65536, undone in the page
packed = base64.b64encode(gzip.compress(deltas.astype("<u2").tobytes(), 9)).decode()

pid = person["id"]
focals = [json.loads(z.read(f))["focal_length"] for f in z.namelist()
          if f.startswith(f"focal_4d_individual/{pid}/") and f.endswith(".json")]
ply = next(f for f in z.namelist() if f.startswith(f"mesh_4d_individual/{pid}/") and f.endswith(".ply"))
head = z.read(ply)[:2000].decode("latin-1")
full_vertices = int(head.split("element vertex ")[1].split()[0])

others = len(anim["people"]) - 1
data = {
    "fps": anim["fps"], "totalFrames": TOTAL_FRAMES, "height": HEIGHT,
    "focal": statistics.median(focals), "frames": person["frames"],
    "lo": person["lo"], "hi": person["hi"], "vertexCount": n, "fullVertexCount": full_vertices,
    "faces": person["faces"], "packed": packed,
    "note": "The 3D body is a simplified copy of SAM-Body4D's mesh (same points every frame), positioned as the "
            "model placed it relative to the camera. Camera view uses its estimated focal length "
            f"({statistics.median(focals):.0f} px)."
            + (f" SAM-Body4D also tracked {others} other figure(s); only the main dancer is shown." if others else ""),
}

def small_video(src_bytes):
    """Re-encode to 540p H.264, no audio, keyframe every 12 frames so seeking is snappy."""
    import subprocess, tempfile, imageio_ffmpeg
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d, "in.mp4"), Path(d, "out.mp4")
        src.write_bytes(src_bytes)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-i", str(src), "-an",
                        "-vf", "scale=-2:540", "-c:v", "libx264", "-crf", "28", "-g", "12", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(dst)], check=True)
        return dst.read_bytes()

def data_uri(b, mime="video/mp4"):
    return f"data:{mime};base64," + base64.b64encode(b).decode()

html = (HERE / "template.html").read_text(encoding="utf-8")
html = html.replace("__DATA__", json.dumps(data, separators=(",", ":")))
html = html.replace("__DEMO__", data_uri(small_video(Path(demo_path).read_bytes())))
html = html.replace("__OVERLAY__", data_uri(small_video(z.read("overlay.mp4"))))
Path(out_path).write_text(html, encoding="utf-8")
print(f"{len(person['frames'])} meshes, {n} points; packed mesh {len(packed) / 1e6:.1f} MB; "
      f"page {Path(out_path).stat().st_size / 1e6:.1f} MB")
