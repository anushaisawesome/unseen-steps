// YOLO11n-pose in the browser (ONNX Runtime Web; WebGPU where available, else WebAssembly).
// One frame in, the main dancer's box and 17 COCO keypoints out, in video pixels. Nothing leaves the device.

const SIZE = 640;  // the model's fixed input (exported with imgsz=640)
const canvas = new OffscreenCanvas(SIZE, SIZE);
const ctx = canvas.getContext("2d", { willReadFrequently: true });
let session = null;

export async function loadPose(onProgress) {
  const ort = window.ort;
  ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";
  onProgress?.("Downloading the pose model (12 MB, once)…");
  const model = await (await fetch("models/yolo11n-pose.onnx")).arrayBuffer();
  onProgress?.("Starting the pose model…");
  const providers = "gpu" in navigator ? ["webgpu", "wasm"] : ["wasm"];
  session = await ort.InferenceSession.create(model, { executionProviders: providers });
  return providers[0];
}

// Letterbox the frame into 640x640 (grey padding), as Ultralytics does.
function preprocess(video) {
  const w = video.videoWidth, h = video.videoHeight;
  const scale = SIZE / Math.max(w, h);
  ctx.fillStyle = "rgb(114,114,114)";
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.drawImage(video, 0, 0, w * scale, h * scale);
  const px = ctx.getImageData(0, 0, SIZE, SIZE).data;
  const input = new Float32Array(3 * SIZE * SIZE);
  for (let i = 0, p = 0; i < SIZE * SIZE; i++, p += 4) {
    input[i] = px[p] / 255;
    input[i + SIZE * SIZE] = px[p + 1] / 255;
    input[i + 2 * SIZE * SIZE] = px[p + 2] / 255;
  }
  return { input, scale };
}

// Output is [1, 56, 8400]: per candidate cx, cy, w, h, confidence, then 17 x (x, y, visibility).
// Solo dancer: keep the biggest confident person.
export async function detect(video, minConf = 0.25) {
  const { input, scale } = preprocess(video);
  const tensor = new window.ort.Tensor("float32", input, [1, 3, SIZE, SIZE]);
  const out = (await session.run({ images: tensor })).output0.data;
  const N = 8400;
  let best = -1, bestArea = 0;
  for (let i = 0; i < N; i++) {
    if (out[4 * N + i] < minConf) continue;
    const area = out[2 * N + i] * out[3 * N + i];
    if (area > bestArea) { bestArea = area; best = i; }
  }
  if (best < 0) return null;
  const at = (row) => out[row * N + best] / scale;
  const box = [at(0) - at(2) / 2, at(1) - at(3) / 2, at(0) + at(2) / 2, at(1) + at(3) / 2];
  const kp = [];
  for (let k = 0; k < 17; k++) kp.push([at(5 + 3 * k), at(6 + 3 * k), out[(7 + 3 * k) * N + best]]);
  return { box, kp, conf: out[4 * N + best] };
}
