# Quick Start (AMD ROCm, Radeon PRO W7900 / gfx1100)

Status legend: ✅ = command executed successfully on the W7900 during the
2026-11 publication-readiness mission (exact receipt paths in
`docs/EVIDENCE_INDEX.md`); 🔬 = documented but pending W7900 verification.

## 0. Environment diagnostic

```bash
git clone https://github.com/AIwork4me/YuE2-SGLang-ROCm.git
cd YuE2-SGLang-ROCm
python3 scripts/check_environment.py          # ✅
```

## 1. Materialize the pinned workspace (models, dataset, evaluator)

```bash
export YUE2_WORKSPACE=/data/yue2              # any large-volume dir
python3 scripts/download_pins.py --workspace $YUE2_WORKSPACE   # ✅ ALL PINS VERIFIED (SHA256)
```

## 2. Choose your path

### Path A — native PyTorch (official YuE2 pipeline)

```bash
python3.12 -m venv $YUE2_WORKSPACE/environments/yue2-torch
source $YUE2_WORKSPACE/environments/yue2-torch/bin/activate
pip install --index-url https://download.pytorch.org/whl/rocm7.1 \
    "torch==2.10.0+rocm7.1" "torchaudio==2.10.0+rocm7.1"        # ✅ (gfx1100 verified)
pip install "transformers==4.57.6" "safetensors==0.7.0" "tiktoken==0.12.0" \
    "numpy==2.2.6" "soundfile==0.13.1" "accelerate==1.13.0" "huggingface-hub==0.36.2"
pip install --no-deps $YUE2_WORKSPACE/models/YuE2-3B/yue2_infer-0.1.3-py3-none-any.whl
```

Generate the official benchmark pilot (torch-eager is the ROCm backend — see
`docs/TROUBLESHOOTING.md`):

```bash
cd $YUE2_WORKSPACE/benchmark/WildSongBench
python code/generate.py --backend torch-eager --candidates 2 \
    --prompt-index 0 --output $YUE2_WORKSPACE/runs/pilot0 \
    --cache-dir $YUE2_WORKSPACE/hf-cache                     # ✅ 2/2 complete, 191s/155s songs
```

Shortest first song via the Python API: see `docs/PYTORCH_API.md`. 🔬
(dev-path verification scheduled; benchmark path above is verified)

### Path B — SGLang serving (HTTP)

```bash
bash scripts/setup_gfx1100_rocm7141.sh          # torch 2.12.0+rocm7.14.1 venv ✅
# apply patches 0001-0005 + 0008 to $YUE2_WORKSPACE/upstream/sglang (frozen campaign stack) ✅
YUE2_WORKSPACE=$YUE2_WORKSPACE bash scripts/setup_sglang_gfx1100.sh       # ✅
YUE2_WORKSPACE=$YUE2_WORKSPACE bash scripts/serve_yue2_gfx1100.sh         # ✅ health OK on :31000
curl http://127.0.0.1:31000/health                                       # ✅ {"status":"ok"}

# one generation (48 kHz stereo + full artifact bundle):
python3 - <<'PY'                                                          # ✅ 12s audio verified
import json, urllib.request
payload = {"style": "[Tags]\nsoft pop\n", "lyrics": "[Lyrics]\nA tiny phrase.\n",
           "seed": 700001, "cot": "full", "ode_steps": 4, "semantic_max_tokens": 300,
           "output_path": "/tmp/yue2", "output_file_name": "v.wav",
           "artifacts_dir": "/tmp/yue2/c1", "id": "first"}
req = urllib.request.Request("http://127.0.0.1:31000/v1/audio/generations",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"})
print(urllib.request.urlopen(req, timeout=900).read().decode()[:200])
PY
```

Details, limits and the exact flag matrix: `docs/SGLANG_API.md`,
`docs/COMPATIBILITY_MATRIX.md`.

## 3. Reproduce the official WildSongBench benchmark

See `docs/BENCHMARK_REPRODUCTION.md` (full 192×2 protocol) — ✅ harness
verified on this hardware; campaign artifacts under
`evidence/publication/`.

## 4. What to expect

| Path | VRAM (peak observed) | Speed (W7900) |
|---|---|---|
| PyTorch torch-eager (full song, budget 24 GiB) | ~9–14 GiB during pilot | ~7 min per song |
| SGLang server (full song, official params) | server idle ~11 GiB; generating up to ~41 GiB | ~4 min per song (245 s median) |

Numbers are from this mission's receipts, not marketing: see
`docs/RESULTS.md` for the full measurement methodology.
