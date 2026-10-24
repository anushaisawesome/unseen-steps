"""Generate sam_body4d_first30.ipynb: SAM-Body4D on the first 30 s of any uploaded video, joints only.

python scripts/sam_body4d/make_nb_first30.py scripts/sam_body4d/sam_body4d_first30.ipynb
Edit this file, not the .ipynb.

Same rules as the narration pipeline (scripts/killtest.py): only the first 30 seconds of every video, at the
video's own frame rate (every frame, no resampling), so YOLO and SAM-Body4D see exactly the same frames.
"""
import json, sys

SECONDS = 30      # analyse only the first 30 s of every video
BATCH = 8         # frames per SAM 3D Body batch (64 in the repo's config; memory grows with dancers x batch)

cells = []
def md(s): cells.append({"cell_type": "markdown", "metadata": {}, "source": s.strip()})
def code(s): cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip()})

md(f"""
# SAM-Body4D: first {SECONDS} seconds of a video

Runs [SAM-Body4D](https://github.com/gaomingqi/sam-body4d) on the first {SECONDS} seconds of a video you upload, and saves
**3D joints for every dancer in every frame** for the Unseen Steps narration (`server/body3d.py`).

**How to run**
1. *Runtime → Change runtime type →* **A100**.
2. *Runtime → Run all*. Cell 1 asks you to choose a file: pick the full video (e.g. `judas.mp4`).
   The notebook keeps the first {SECONDS} s at the video's own frame rate: every frame, nothing resampled.
3. Setup ~20–25 min. The run depends on the number of dancers: about 10 min for a soloist, roughly
   1.5–2.5 hours for 20 dancers at 24 fps. Cell 8 prints progress every minute; keep the tab open.
   At the end it downloads `sam_body4d_<video name>.zip`.

**Details**
- Only joints are saved, not 3D meshes: meshes for 20 dancers would be gigabytes.
- SAM 3D Body processes {BATCH} frames at a time instead of 64, and SAM 3 keeps video frames in normal memory
  instead of on the GPU, so large groups fit.
- Who to follow: it checks a frame every half second over the first 15 s and follows everyone detected in the
  frame where it sees the most people. Anyone who only enters later isn't tracked.
- Same setup as before: SAM-Body4D runs in its own Python 3.12 environment (Colab is 3.13; SAM 3 pins
  `numpy==1.26`); Detectron2 is built without its CUDA kernels (this model doesn't need them); `setuptools<81`;
  `MPLBACKEND=Agg`. SAM 3 and SAM 3D Body come from public mirrors (Meta's repos are gated), checked against
  SHA256 hashes. Every step logs to `/content/logs/`; a failing cell prints the end of its log.
""")

code(f"""
# 1. Upload a video, then keep its first {SECONDS} s at its own frame rate (re-encoded so the cut is exact;
#    no audio, SAM-Body4D doesn't use it)
import os, subprocess, json
from google.colab import files
os.makedirs("/content/clip", exist_ok=True)
up = files.upload()
NAME = next(iter(up))
STEM = os.path.splitext(NAME)[0]
os.replace(NAME, "/content/clip/full" + os.path.splitext(NAME)[1])
SRC = "/content/clip/full" + os.path.splitext(NAME)[1]
CLIP = "/content/clip/clip.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", SRC, "-t", "{SECONDS}", "-an", "-c:v", "libx264", "-crf", "18",
                "-pix_fmt", "yuv420p", CLIP], check=True)
probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                   "stream=avg_frame_rate,nb_read_frames,width,height", "-of", "json", CLIP],
                                  capture_output=True, text=True).stdout)["streams"][0]
num, den = map(int, probe["avg_frame_rate"].split("/"))
FPS = num / den
FRAMES = int(probe["nb_read_frames"])
print(f"{{NAME}}: kept the first {SECONDS} s: {{FRAMES}} frames at {{FPS:.3f}} fps, {{probe['width']}}x{{probe['height']}}")
""")

code("""
# 2. Check the GPU, and a helper that runs a shell step, logs it, and stops on failure
import sys
os.makedirs("/content/logs", exist_ok=True)

def run(name, cmd, env=None):
    log = f"/content/logs/{name}.log"
    print(f"[{name}] ...", end=" ", flush=True)
    with open(log, "w") as f:
        # MPLBACKEND: Colab points matplotlib at its notebook backend, which the separate env doesn't have
        p = subprocess.run(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT, executable="/bin/bash",
                           env={**os.environ, "MPLBACKEND": "Agg", **(env or {})})
    if p.returncode != 0:
        print("FAILED\\n" + "".join(open(log).readlines()[-40:]))
        raise RuntimeError(f"step '{name}' failed (full log: {log}). Paste the output above to Claude.")
    print("ok")

out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                     capture_output=True, text=True).stdout.strip()
print(out)
gpu, mem = out.split(", ")
assert int(mem) >= 39000, f"{gpu} has {mem} MiB; switch the runtime to an A100."
""")

code("""
# 3. Python 3.12 environment (micromamba) and system libraries for headless rendering
ENV = "/content/env"
PY = f"{ENV}/bin/python"
run("apt", "apt-get -qq update && apt-get -qq install -y libegl1 libgl1 libgles2 libglib2.0-0 ffmpeg zip")
run("micromamba", "curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C /content bin/micromamba")
run("env", f"/content/bin/micromamba create -y -p {ENV} -c conda-forge python=3.12 pip")
# setuptools < 81: Detectron2's model zoo still imports pkg_resources, which 81 removed
run("pip-tools", f"{PY} -m pip install -U pip 'setuptools<81' wheel ninja")
""")

code("""
# 4. SAM-Body4D and its dependencies (the Detectron2 build takes ~5 min)
run("clone", "rm -rf /content/sam-body4d && git clone -q https://github.com/gaomingqi/sam-body4d /content/sam-body4d")
run("torch", f"{PY} -m pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 "
             "--index-url https://download.pytorch.org/whl/cu126")
run("detectron2", f"{PY} -m pip install 'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' "
                  "--no-build-isolation --no-deps", env={"CUDA_VISIBLE_DEVICES": "", "FORCE_CUDA": "0"})
run("sam3", f"cd /content/sam-body4d && {PY} -m pip install -e models/sam3")
run("body4d", f"cd /content/sam-body4d && {PY} -m pip install -e .")
run("check", f"{PY} -c \\"import torch, detectron2, sam3, numpy; "
             "print('torch', torch.__version__, torch.cuda.is_available(), 'numpy', numpy.__version__)\\"")
print(open("/content/logs/check.log").read())
""")

code("""
# 5. The two gated Meta checkpoints from public mirrors (no login), placed where setup.py expects them.
#    cubert-gmbh lists Meta's own SHA256 for sam3.pt; the SAM 3D Body mirrors (gokayokyay, Blendcap) agree.
import hashlib, shutil
from huggingface_hub import hf_hub_download
os.environ.pop("HF_TOKEN", None)
CK = "/content/checkpoints"
MIRRORS = [
    ("cubert-gmbh/sam3", "sam3.pt", "sam3/sam3.pt",
     "9999e2341ceef5e136daa386eecb55cb414446a00ac2b55eb2dfd2f7c3cf8c9e"),
    ("gokayokyay/sam-3d-body", "model.ckpt", "sam-3d-body-dinov3/model.ckpt",
     "b5a2f9d305dd02626b967aa2e86021fba07065df66ce7a7e00ffb9664f150abf"),
    ("gokayokyay/sam-3d-body", "assets/mhr_model.pt", "sam-3d-body-dinov3/assets/mhr_model.pt",
     "352e271a6c42729c68554ceaea0c955e866970160c31e35506d782dc0f7377bc"),
    ("gokayokyay/sam-3d-body", "model_config.yaml", "sam-3d-body-dinov3/model_config.yaml", None),
]
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()
for repo, fn, rel, want in MIRRORS:
    dst = os.path.join(CK, rel)
    if not os.path.exists(dst):
        src = hf_hub_download(repo, fn, token=False)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(os.path.realpath(src), dst)
    if want:
        got = sha256(dst)
        assert got == want, f"{repo}/{fn}: sha256 {got} != expected {want}"
    print("ok", rel)
""")

code(f"""
# 6. Remaining checkpoints, then the config: no diffusion occlusion fill (slow, and memory grows with dancers),
#    and {BATCH} frames per SAM 3D Body batch so large groups fit in memory.
run("checkpoints", f"cd /content/sam-body4d && {{PY}} scripts/setup.py --ckpt-root {{CK}}")
print("".join(open("/content/logs/checkpoints.log").readlines()[-15:]))
run("config", f"cd /content/sam-body4d && {{PY}} -c \\"from omegaconf import OmegaConf; "
              "c = OmegaConf.load('configs/body4d.yaml'); c.completion.enable = False; "
              "c.sam_3d_body.batch_size = {BATCH}; OmegaConf.save(c, 'configs/body4d.yaml')\\"")
print(open("/content/sam-body4d/configs/body4d.yaml").read())
""")

code("""
# 7. Patches to SAM-Body4D (each checked against the upstream code; restored first so re-running is safe)
def patch(path, pairs):
    run("restore", f"cd /content/sam-body4d && git checkout -- {path}")
    full = f"/content/sam-body4d/{path}"
    s = open(full).read()
    for old, new in pairs:
        assert old in s, f"{path} has changed upstream (missing: {old[:60]!r}): send this to Claude"
        s = s.replace(old, new, 1)
    open(full, "w").write(s)
    run("compile", f"{PY} -m py_compile {full}")

# a) Save the 70 MHR joints per dancer and frame (*_kp3d.npy; camera translation added, then rotated 180 degrees
#    about x, the axes the .ply meshes use), and skip the .ply export: 20 dancers' meshes would be gigabytes.
json_line = "            json.dump(focal_length, f, indent=4)\\n"
patch("models/sam_3d_body/notebook/utils.py", [
    ("        tmesh.export(mesh_path)\\n", ""),
    (json_line, json_line +
        "        kp = np.asarray(person_output['pred_keypoints_3d'])[:70]\\n"
        "        kp = kp + np.asarray(person_output['pred_cam_t'])\\n"
        "        kp = kp * np.array([1, -1, -1])\\n"
        "        name = os.path.basename(image_path)[:-4]\\n"
        "        np.save(f'{focal_dir}/{pid+1}/{name}_kp3d.npy', kp)\\n"),
])

# b) Who to follow: upstream takes the first frame (from frame 10) where anyone is detected; a video that opens
#    on black or fades in would lose most of a group. Check a frame every half second over the first 15 s and
#    follow everyone in the frame with the most people.
# c) Keep video frames and tracking state in normal memory (SAM 3's own options), so ~700+ frames fit.
# d) Lift the 1800-frame tracking cap (30 s at 60 fps is exactly 1800).
# e) Skip the per-dancer render images: 20 dancers x every frame adds hours; the combined render is kept.
half, last = max(1, round(FPS / 2)), min(FRAMES - 1, round(FPS * 15))
patch("scripts/offline_app.py", [
    ("        for starting_frame_idx in range(10, 100):\\n"
     "            image = np.array(read_frame_at(args.input_video, starting_frame_idx))\\n"
     "            outputs = predictor.sam3_3d_body_model.process_one_image(image, bbox_thr=0.6,)\\n"
     "            if len(outputs) > 0:\\n"
     "                break\\n",
     "        best = (-1, None, None)\\n"
     f"        for idx in range({half}, {last} + 1, {half}):\\n"
     "            frame = read_frame_at(args.input_video, idx)\\n"
     "            if frame is None:\\n"
     "                break\\n"
     "            found = predictor.sam3_3d_body_model.process_one_image(np.array(frame), bbox_thr=0.6,)\\n"
     "            print(f'frame {idx}: {len(found)} people detected', flush=True)\\n"
     "            if len(found) > best[0]:\\n"
     "                best = (len(found), idx, found)\\n"
     "        _, starting_frame_idx, outputs = best\\n"
     "        print(f'following {len(outputs)} people from frame {starting_frame_idx}', flush=True)\\n"),
    ("        inference_state = predictor.predictor.init_state(video_path=args.input_video)\\n",
     "        inference_state = predictor.predictor.init_state(video_path=args.input_video,\\n"
     "                                                         offload_video_to_cpu=True, offload_state_to_cpu=True)\\n"),
    ("max_frame_num_to_track: int = 1800", "max_frame_num_to_track: int = 100000"),
    ("                rend_img_list = visualize_sample(img, mask_output, self.sam3_3d_body_model.faces, id_current)\\n",
     "                rend_img_list = []\\n"),
])
""")

code("""
# 8. Run SAM-Body4D, printing progress every minute (about 10 min for a soloist, 1.5-2.5 h for 20 dancers)
import time
log = "/content/logs/body4d-run.log"
cmd = (f"cd /content/sam-body4d && rm -rf /content/out && "
       f"{PY} scripts/offline_app.py --input_video {CLIP} --output_dir /content/out")
with open(log, "w") as f:
    proc = subprocess.Popen(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT, executable="/bin/bash",
                            env={**os.environ, "MPLBACKEND": "Agg", "PYOPENGL_PLATFORM": "egl",
                                 "PYTHONPATH": "/content/sam-body4d/models/sam3"})
start = time.time()
while proc.poll() is None:
    time.sleep(60)
    text = open(log, errors="replace").read().replace("\\r", "\\n").strip().splitlines()
    print(f"{(time.time() - start) / 60:5.0f} min | {text[-1][:150] if text else '(starting)'}", flush=True)
if proc.returncode != 0:
    print("FAILED\\n" + "".join(open(log, errors="replace").readlines()[-40:]))
    raise RuntimeError(f"SAM-Body4D failed (full log: {log}). Paste the output above to Claude.")
!grep -m1 "following" /content/logs/body4d-run.log
dancers = sorted(os.listdir("/content/out/focal_4d_individual"), key=int)
counts = {d: len([f for f in os.listdir(f"/content/out/focal_4d_individual/{d}") if f.endswith("_kp3d.npy")])
          for d in dancers}
print(f"{len(dancers)} dancers tracked over {FRAMES} frames; frames with joints per dancer: {counts}")
""")

code("""
# 9. Watch SAM-Body4D's render (it always writes 25 fps; -r before the input restores the clip's real speed)
import glob
from IPython.display import Video
src = sorted(glob.glob("/content/out/4d_*.mp4"))[-1]
run("overlay", f"ffmpeg -v error -y -r {FPS} -i {src} -vf scale=-2:720 -c:v libx264 -crf 26 "
               "-pix_fmt yuv420p -movflags +faststart /content/out/overlay.mp4")
Video("/content/out/overlay.mp4", embed=True, width=720)
""")

code(f"""
# 10. Zip and download. Put the zip in your Downloads folder and tell Claude.
json.dump({{"clip": NAME, "seconds": {SECONDS}, "fps": FPS, "frames": FRAMES, "dancers": len(dancers)}},
          open("/content/out/meta.json", "w"))
ZIP = f"/content/sam_body4d_{{STEM}}.zip"
run("zip", f"cd /content/out && rm -f {{ZIP}} && zip -q -r {{ZIP}} meta.json overlay.mp4 focal_4d_individual")
!ls -lh {{ZIP}}
files.download(ZIP)
""")

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "A100", "provenance": []},
      "kernelspec": {"display_name": "Python 3", "name": "python3"}, "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 0}
json.dump(nb, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
