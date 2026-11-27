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

## 8. RC5 path — the author's LATEST upstream head with native capability gates

Since upstream commit `2a816358d` the tree gates its CUDA-only fast paths on
real capability, so no `SGLANG_YUE2_*` force-flag is needed. Two small
import-guard patches are still required (they fix `aiter` / `sgl_kernel`
imports that otherwise make `sglang serve` fall back to the LLM backend).

```bash
export YUE2_WORKSPACE=/data/yue2
# 1. generation venv: torch 2.12.0+rocm7.14.1 (device-gfx1100) from the AMD index
bash scripts/campaign_ops/rc5_build_generation_env.sh
# 2. pinned downloads, every file SHA256-gated
python3 scripts/download_pins.py --workspace "$YUE2_WORKSPACE"
# 3. the frozen PR head (never the merge ref) + the two import-guard patches
git clone --branch add_yue2 https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork.git "$YUE2_WORKSPACE/upstream/sglang-latest"
git -C "$YUE2_WORKSPACE/upstream/sglang-latest" checkout c67d541a40f8bf851e9fc1e925f5316638838cd6
git -C "$YUE2_WORKSPACE/upstream/sglang-latest" apply patches/rc5-0001-0003-0008-rocm-import-guards.patch
bash scripts/campaign_ops/rc5_install_sglang.sh
# 4. prove that the imported SGLang IS the audited tree
source "$YUE2_WORKSPACE/environments/generation/bin/activate"
python scripts/rc5_runtime_manifest.py --sglang-src "$YUE2_WORKSPACE/upstream/sglang-latest" \
  --patch-file patches/rc5-0001-0003-0008-rocm-import-guards.patch \
  --out "$YUE2_WORKSPACE/logs/effective_runtime_manifest.json"
```

Serve and generate under the single-owner lifecycle supervisor (GPU lock,
identity, readiness, verified stop — all in one process):

```bash
bash scripts/campaign_ops/run_with_server.sh --log-dir /tmp/rws -- \
  curl -sS -X POST http://127.0.0.1:31000/v1/audio/generations \
    -H 'Content-Type: application/json' -d '{"style":"[Tags]\nsoft pop\n","lyrics":"[Lyrics]\nA short test phrase.\n","seed":831001,"output_path":"/tmp/yue","output_file_name":"song.wav"}'
```

`YUE2_SERVE_SCRIPT=scripts/serve_yue2_rc5.sh` selects the native-gate serve
script (the RC5 campaign default); without it the historical force-flag
matrix is used. Full campaign, checkpoints and resume:

```bash
bash scripts/campaign_ops/rc5_supervise.sh /data/yue2-runs/<run>/wsb_full <run_id>
python scripts/rc5_backup.py verify --run-dir /data/yue2-runs/<run>/wsb_full
```

## What runs and what doesn't (short version)

| Path | Status on gfx1100 |
|---|---|
| AR decode (reference sampler, HIP graphs, ATen flash) | **works** (validated vs eager: 0.0000 logit diff) |
| NAR (reference torch solver) | **works** |
| VAE fp32 tiled decode | **works** |
| DeepSelect fast sampler / batched AR / fused decode+NAR (sgl_kernel) | not available on ROCm — auto-fallback to reference paths |

Details and evidence: `reports/gfx1100/PHASE4_SOURCE_BUILD.md`.

## RC5.1 verified paths (latest upstream c67d541a, 2026-11-27)

The commands below are the exact, end-to-end verified sequence for the
latest-upstream reproduction (384 candidates + five metrics). See
`docs/BENCHMARK_REPRODUCTION.md` (RC5.1 section) for the full listing and
`reports/w7900_rc5/rc5_1/` for the evidence of the run they reproduce.

- Generation: `scripts/campaign_ops/rc5_supervise.sh <run_dir> <run_id>` —
  crash-resilient, resumable, checkpoints every 16 candidates plus on pause;
  second-volume backup via `RC5_BACKUP_DIR`.
- Disaster recovery: `python scripts/rc5_backup.py drill --from
  <backup checkpoints dir> --to <fresh dir>` (384/384 verified).
- Q3O on 48 GB: `scripts/rc5_q3o_judge.py` (34 GPU + 14 CPU MoE layers;
  needs the vllm-rocm venv; the judge content-hashes the model and binds
  every receipt to a run identity).
- If vLLM fails to start on ROCm with "Device string must not be empty":
  that is the amdsmi platform-probe failure — `rc5_asr_vllm_native.py`
  already contains the workaround (platform registered + in-process engine).
- If a Q3O/ASR process segfaults (rc=139) in llvmlite during librosa import:
  compile numba kernels BEFORE torch loads (the judge and per-lab do this
  automatically now).
