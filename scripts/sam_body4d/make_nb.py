import json, sys

cells = []
def md(s): cells.append({"cell_type": "markdown", "metadata": {}, "source": s.strip()})
def code(s): cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip()})

md("""
# SAM-Body4D on the Unseen Steps ballet clip

Runs [SAM-Body4D](https://github.com/gaomingqi/sam-body4d) on the ballet demo footage (Mixkit clip 956, the clean
version of `docs/media/ballet-demo.mp4`) and packs the 3D body meshes into one small file for the 3D viewer.

**How to run:** *Runtime → Change runtime type →* **A100** (or L4). Then *Runtime → Run all*.
Setup ~20–25 min, the run ~5 min. At the end it downloads `sam_body4d_ballet.zip`.

**How it's set up**
- SAM-Body4D is built for Python 3.12, but Colab now runs 3.13 (SAM 3 pins `numpy==1.26`, which has no 3.13 build).
  So everything runs in its own Python 3.12 environment at `/content/env`, made with micromamba.
- Detectron2 (the person detector) is compiled without its own CUDA kernels: the parts this model uses run on
  torchvision's GPU ops, so nothing is lost, and it avoids a CUDA compiler mismatch with Colab.
- No Hugging Face login: the two gated Meta models (SAM 3, SAM 3D Body) come from public mirrors that
  redistribute them under Meta's SAM License, checked against SHA256 hashes.
- Every step logs to `/content/logs/`; if one fails, the cell stops and prints the end of that log.
""")

code("""
# 1. Check the GPU, and set up a helper that runs a shell step, logs it, and stops on failure
import os, subprocess, sys
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
name, mem = out.split(", ")
assert int(mem) >= 20000, f"{name} has {mem} MiB; switch the runtime to an A100 or L4 GPU."
""")

code("""
# 2. Python 3.12 environment (micromamba) and system libraries for headless rendering
ENV = "/content/env"
PY = f"{ENV}/bin/python"
run("apt", "apt-get -qq update && apt-get -qq install -y libegl1 libgl1 libgles2 libglib2.0-0 ffmpeg zip")
run("micromamba", "curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C /content bin/micromamba")
run("env", f"/content/bin/micromamba create -y -p {ENV} -c conda-forge python=3.12 pip")
# setuptools < 81: Detectron2's model zoo still imports pkg_resources, which 81 removed
run("pip-tools", f"{PY} -m pip install -U pip 'setuptools<81' wheel ninja")
print(subprocess.run([PY, "--version"], capture_output=True, text=True).stdout)
""")

code("""
# 3. SAM-Body4D and its dependencies (the Detectron2 build takes ~5 min)
%cd /content
run("clone", "rm -rf /content/sam-body4d && git clone -q https://github.com/gaomingqi/sam-body4d /content/sam-body4d")
%cd /content/sam-body4d
run("torch", f"{PY} -m pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 "
             "--index-url https://download.pytorch.org/whl/cu126")
# CUDA hidden during the build so Detectron2 compiles its CPU ops only (see the note at the top)
run("detectron2", f"{PY} -m pip install 'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' "
                  "--no-build-isolation --no-deps", env={"CUDA_VISIBLE_DEVICES": "", "FORCE_CUDA": "0"})
run("sam3", f"{PY} -m pip install -e models/sam3")
run("body4d", f"{PY} -m pip install -e .")
run("extras", f"{PY} -m pip install fast-simplification trimesh scipy")
run("check", f"{PY} -c \\"import torch, detectron2, sam3, numpy; "
             "print('torch', torch.__version__, torch.cuda.is_available(), 'numpy', numpy.__version__)\\"")
print(open("/content/logs/check.log").read())
""")

code("""
# 4. The two gated Meta checkpoints from public mirrors (no login), placed where setup.py expects them
#    so it skips them. cubert-gmbh's README lists Meta's own SHA256 for sam3.pt; the two SAM 3D Body
#    mirrors (gokayokyay, Blendcap) carry identical hashes, and all sizes match Meta's repos.
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

code("""
# 5. The remaining (ungated) checkpoints, then turn off the diffusion occlusion fill:
#    one dancer and nothing in front of her, so it would only cost time and memory.
run("checkpoints", f"cd /content/sam-body4d && {PY} scripts/setup.py --ckpt-root {CK}")
print("".join(open("/content/logs/checkpoints.log").readlines()[-15:]))
run("config", f"cd /content/sam-body4d && {PY} -c \\"from omegaconf import OmegaConf; "
              "c = OmegaConf.load('configs/body4d.yaml'); c.completion.enable = False; "
              "OmegaConf.save(c, 'configs/body4d.yaml')\\"")
print(open("/content/sam-body4d/configs/body4d.yaml").read())
""")

code("""
# 6. The ballet clip: Mixkit 956 "A young ballerina dancing in a white room" (same source as
#    scripts/get_demo_clip.sh), the clean footage under docs/media/ballet-demo.mp4: 547 frames, 24 fps.
#    Kept at 24 fps so frame N here is frame N of the demo video.
os.makedirs("/content/clip", exist_ok=True)
run("clip", "curl -sSfL -o /content/clip/mix956.mp4 https://assets.mixkit.co/videos/956/956-720.mp4 && "
            "ffmpeg -v error -y -i /content/clip/mix956.mp4 -an -c:v copy /content/clip/ballet.mp4")
!ffprobe -v error -show_entries format=duration:stream=width,height,r_frame_rate -of compact /content/clip/ballet.mp4
""")

code("""
# 7. Run SAM-Body4D (~5 min on an A100)
run("body4d-run", f"cd /content/sam-body4d && rm -rf /content/out && "
                  f"{PY} scripts/offline_app.py --input_video /content/clip/ballet.mp4 --output_dir /content/out",
    env={"PYOPENGL_PLATFORM": "egl", "PYTHONPATH": "/content/sam-body4d/models/sam3"})
print("".join(open("/content/logs/body4d-run.log").readlines()[-10:]))
!ls /content/out
!for d in /content/out/mesh_4d_individual/*/; do echo "$d: $(ls $d | wc -l) meshes"; done
""")

code("""
# 8. Watch the rendered overlay (re-encoded to H.264 so browsers play it). SAM-Body4D writes it at
#    25 fps; -r 24 before the input restores the clip's real speed.
import glob
from IPython.display import Video
src = sorted(glob.glob("/content/out/4d_*.mp4"))[-1]
run("overlay", f"ffmpeg -v error -y -r 24 -i {src} -vf scale=-2:720 -c:v libx264 -crf 26 "
               "-pix_fmt yuv420p -movflags +faststart /content/out/overlay.mp4")
Video("/content/out/overlay.mp4", embed=True, width=720)
""")

code("""
%%writefile /content/pack.py
# Pack the meshes for the 3D viewer: a simplified copy of the body (the same simplification applied
# to every frame, so it animates), quantised to 16 bits.
import base64, glob, json, os, re
import numpy as np, trimesh, fast_simplification
from scipy.spatial import cKDTree

FPS = 24
root = "/content/out/mesh_4d_individual"
people = sorted(os.listdir(root), key=int)
anim = {"fps": FPS, "people": []}
for pid in people:
    plys = sorted(glob.glob(f"{root}/{pid}/*.ply"))
    m0 = trimesh.load(plys[0], process=False)
    pts, faces = fast_simplification.simplify(m0.vertices.astype(np.float32), m0.faces.astype(np.int32),
                                              target_reduction=0.85)
    keep = cKDTree(m0.vertices).query(pts)[1]
    V = np.stack([trimesh.load(p, process=False).vertices[keep] for p in plys]).astype(np.float32)
    frames = [int(re.search(r"(\\d+)\\.ply$", p).group(1)) for p in plys]
    lo, hi = V.min(axis=(0, 1)), V.max(axis=(0, 1))
    q = np.round((V - lo) / (hi - lo) * 65535).astype("<u2")
    anim["people"].append({
        "id": int(pid), "frames": frames, "lo": lo.tolist(), "hi": hi.tolist(),
        "vertexCount": int(len(keep)), "faces": faces.astype(int).ravel().tolist(),
        "vertices": base64.b64encode(q.tobytes()).decode(),
    })
    print(f"person {pid}: {len(plys)} frames, {len(m0.vertices)} -> {len(keep)} vertices")
with open("/content/out/anim.json", "w") as f:
    json.dump(anim, f)
print("anim.json:", os.path.getsize("/content/out/anim.json") // 1024, "KB")
""")

code("""
# 9. Pack, zip and download. Put sam_body4d_ballet.zip in your Downloads folder and tell Claude.
run("pack", f"{PY} /content/pack.py")
print(open("/content/logs/pack.log").read())
run("zip", "cd /content/out && rm -f /content/sam_body4d_ballet.zip && zip -q -r /content/sam_body4d_ballet.zip "
           "anim.json overlay.mp4 mesh_4d_individual focal_4d_individual")
!ls -lh /content/sam_body4d_ballet.zip
from google.colab import files
files.download("/content/sam_body4d_ballet.zip")
""")

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "A100", "provenance": []},
      "kernelspec": {"display_name": "Python 3", "name": "python3"}, "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 0}
json.dump(nb, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
