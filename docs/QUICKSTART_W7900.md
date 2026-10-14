# Quickstart: YuE2 on AMD Radeon PRO W7900 (gfx1100) via SGLang + ROCm

Verified path, executed end-to-end on a W7900 test rig (see
`reports/gfx1100/` for the underlying evidence). Any Linux host with a
supported ROCm kernel driver for gfx1100 works; nothing here requires CUDA.

## 0. Prerequisites

- Ubuntu 24.04 (other distributions: adapt package names), kernel with amdgpu
  support for Navi 31, `/dev/kfd` + `/dev/dri/renderD*` accessible to your user.
- ~60 GB free disk for environment + models + example runs.
- `python3.12`, `git`, `ffmpeg`.

One-command environment diagnostic (run this first):

```bash
python3 scripts/check_environment.py          # prints PASS/WARN per subsystem
python3 scripts/check_environment.py --check-torch   # after step 2, verifies GPU compute
```

## 1. Environment (exact ROCm 7.14.1 wheels)

```bash
bash scripts/setup_gfx1100_rocm7141.sh        # idempotent; refuses to clobber a
                                              # non-conforming torch; validates
                                              # real GPU compute at the end
source environments/yue2-gfx1100/bin/activate
```

This installs **exactly** `torch 2.12.0+rocm7.14.1`,
`torchvision 0.27.0+rocm7.14.1`, `torchaudio 2.11.0+rocm7.14.1` from
`repo.amd.com/rocm/whl-multi-arch` (plus the venv-local ROCm 7.14.1 userspace —
`import torch` auto-initializes it via `torch._rocm_init`; no `LD_LIBRARY_PATH`
needed). The host kernel driver is never touched.

## 2. Models (hash-verified)

```bash
python3 scripts/download_pins.py              # YuE2-3B + YuE2-Vae-legacy +
                                              # WildSongBench, full SHA256 pins
```

Pins: `m-a-p/YuE2-3B@1a96eca6`, `m-a-p/YuE2-Vae-legacy@b54118f`,
dataset `m-a-p/WildSongBench@e361b85a`. Set `HF_ENDPOINT=https://hf-mirror.com`
if huggingface.co is unreachable — every file is hash-checked either way.

## 3. SGLang (PR #42106 + minimal ROCm patches)

```bash
cd upstream/sglang                            # codeload tarball of ced0ef7d, git-inited
git apply ../../patches/0001-0005-rocm-compat.patch
git apply ../../patches/0008-kvcacheio-import-guards.patch
cd ../..
SGLANG_BUILD_RUST_EXTS=none pip install --no-deps --no-build-isolation \
  -e upstream/sglang/python -i https://pypi.org/simple
# runtime deps (serving set):
pip install -i https://pypi.org/simple orjson fastapi uvicorn aiohttp msgspec \
  pyzmq psutil prometheus-client transformers==5.17.0 tokenizers==0.23.2 \
  compressed-tensors==0.18.0 huggingface-hub tiktoken soundfile scipy \
  python-multipart outlines==0.1.11 xgrammar pillow requests python-dateutil
```

`--no-build-isolation` matters: sglang's build-system pins a CUDA torch you must
never install. Never `pip install sgl-kernel` on ROCm (PyPI ships a CUDA-only
sm100 build — the YuE2 path is designed to fall back cleanly without it).

## 4. Serve

```bash
bash scripts/serve_yue2_gfx1100.sh            # 127.0.0.1:31000; env overrides:
                                              # HOST PORT GPU_ID MODEL_PATH VAE_PATH
curl http://127.0.0.1:31000/health
```

## 5. Generate

```bash
curl -X POST http://127.0.0.1:31000/v1/audio/generations \
  -H 'Content-Type: application/json' -d '{
    "style": "[Tags]\nsoft pop\n", "lyrics": "[Lyrics]\nA short test phrase.\n",
    "seed": 831001, "output_path": "/tmp/yue", "output_file_name": "song.wav",
    "artifacts_dir": "/tmp/yue/cand1", "id": "demo1",
    "cot": "full", "ode_steps": 32, "semantic_max_tokens": 9000,
    "abc_max_tokens": 4096, "vae_core_frames": 1024, "vae_halo_frames": 16 }'
```

The alias route `/v1/audio/music/generations` behaves identically.
Output: 48 kHz stereo WAV + the official artifact bundle in `artifacts_dir`
(`score.abc`, `semantic.npy`, `latent.npy`, `prefix.npy`, `abc_tokens.npy`,
`plan.json`, `request.json`).

## 6. Verify output

```bash
python - <<'PY'
import soundfile as sf, numpy as np
a, sr = sf.read("/tmp/yue/song.wav", always_2d=True)
assert sr == 48000 and a.shape[1] == 2 and np.isfinite(a).all()
print(f"OK: {len(a)/sr:.1f}s stereo @ {sr} Hz, rms {np.sqrt((a**2).mean()):.3f}")
PY
```

## 7. Optional: WildSongBench reproduction

See `docs/BENCHMARK_REPRODUCTION.md`.

## What runs and what doesn't (short version)

| Path | Status on gfx1100 |
|---|---|
| AR decode (reference sampler, HIP graphs, ATen flash) | **works** (validated vs eager: 0.0000 logit diff) |
| NAR (reference torch solver) | **works** |
| VAE fp32 tiled decode | **works** |
| DeepSelect fast sampler / batched AR / fused decode+NAR (sgl_kernel) | not available on ROCm — auto-fallback to reference paths |

Details and evidence: `reports/gfx1100/PHASE4_SOURCE_BUILD.md`.
