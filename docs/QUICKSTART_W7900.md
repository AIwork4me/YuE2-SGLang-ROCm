# Quickstart: YuE2 on AMD Radeon PRO W7900 (gfx1100) via SGLang + ROCm

**Canonical entry point (RC6, 2026-11-27).** Everything below was executed
end-to-end on a W7900D rig. A new developer needs ONLY this page plus
`docs/TROUBLESHOOTING.md` — the historical engineering reports are not on
the critical path.

The one-command entry point for every step is the reference CLI:

```bash
python3 scripts/reference_cli.py --help      # doctor/install/download/generate/
                                             # verify/benchmark/compare/status/
                                             # resume/stop/package-evidence
```

## 0. Prerequisites

- Linux host with an amdgpu kernel driver for gfx1100 (W7900/W7900D),
  `/dev/kfd` + `/dev/dri/renderD*` accessible to your user.
- ~60 GB free disk for environment + models + example runs
  (full benchmark: ~50 GB more).
- `python3.12`, `git`, `ffmpeg`.
- No root, no driver installation — the ROCm userspace is venv-local.

```bash
python3 scripts/reference_cli.py doctor     # PASS/WARN per subsystem
```

## 1. Install (pinned reference stack, ~25 GB download)

```bash
export YUE2_WORKSPACE=/data/yue2             # any large-volume path
python3 scripts/reference_cli.py install --workspace $YUE2_WORKSPACE
```

This is the frozen RC5.1 reference stack, hash-gated at every step:

| Component | Pin |
|---|---|
| torch | `2.12.0+rocm7.14.1` (AMD index, venv-local ROCm userspace) |
| SGLang | upstream PR #42106 head `c67d541a40f8bf851e9fc1e925f5316638838cd6` (unmerged — snapshot, not a release) |
| patches | `patches/rc5-0001-0003-0008-rocm-import-guards.patch` only (0004/0005 were absorbed upstream) |
| YuE2 model | `m-a-p/YuE2-3B@1a96eca6` |
| VAE | `m-a-p/YuE2-Vae-legacy@b54118f` |
| dataset | `m-a-p/WildSongBench@e361b85a` |

The install ends with a runtime manifest proving the imported SGLang IS the
audited tree (`$YUE2_WORKSPACE/logs/effective_runtime_manifest.json`,
`yue2_runtime_sha256 342b2f53…`).

Manual equivalent (what `install` runs):

```bash
bash scripts/campaign_ops/rc5_build_generation_env.sh
python3 scripts/download_pins.py --workspace $YUE2_WORKSPACE
git clone --branch add_yue2 https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork.git \
    "$YUE2_WORKSPACE/upstream/sglang-latest"
git -C "$YUE2_WORKSPACE/upstream/sglang-latest" checkout c67d541a40f8bf851e9fc1e925f5316638838cd6
# patch path is REPO-ROOT-ABSOLUTE — no CWD dependence:
git -C "$YUE2_WORKSPACE/upstream/sglang-latest" apply \
    /path/to/YuE2-SGLang-ROCm/patches/rc5-0001-0003-0008-rocm-import-guards.patch
bash scripts/campaign_ops/rc5_install_sglang.sh
source "$YUE2_WORKSPACE/environments/generation/bin/activate"
python scripts/rc5_runtime_manifest.py --sglang-src "$YUE2_WORKSPACE/upstream/sglang-latest" \
  --patch-file /path/to/YuE2-SGLang-ROCm/patches/rc5-0001-0003-0008-rocm-import-guards.patch \
  --out "$YUE2_WORKSPACE/logs/effective_runtime_manifest.json"
```

## 2. Generate your first song (GPU, fail-loud)

Original example lyrics are included (safe to publish, unlike WSB lyrics):

```bash
python3 scripts/reference_cli.py generate \
  --lyrics examples/first_song/lyrics_en.txt \
  --style examples/first_song/style.txt \
  --seed 831001 --out-dir $YUE2_WORKSPACE/runs/my-first-song
```

The generation runs under the single-owner lifecycle supervisor:
GPU lock → physical GPU identity → server boot → readiness (not just HTTP
health) → generation → verified stop → lock release. No silent CPU
fallback. Output: `song.wav` (48 kHz stereo) + the official candidate
bundle (score.abc, semantic/latent/prefix/abc_tokens, plan/request/config,
result with model identity hashes).

## 3. Verify your result

```bash
python3 scripts/reference_cli.py verify --run-dir $YUE2_WORKSPACE/runs/my-first-song
# verdict: VERIFIED_REFERENCE_RUN / VERIFIED_WITH_DISCLOSED_DIFFERENCES /
#          VALID_PILOT_ONLY / UNSUPPORTED_CONFIGURATION / INCOMPLETE / FAILED
```

Manual smoke checks:

```bash
python - <<'PY'
import soundfile as sf, numpy as np
a, sr = sf.read("song.wav", always_2d=True)
assert sr == 48000 and a.shape[1] == 2 and np.isfinite(a).all()
print(f"OK: {len(a)/sr:.1f}s stereo @ {sr} Hz, rms {np.sqrt((a**2).mean()):.3f}")
PY
$YUE2_WORKSPACE/environments/yue2-gfx1100/bin/python scripts/gpu_identity.py verify --expect-arch gfx1100
```

## 4. Benchmark pilot (1 h) — then optionally full (24 h + evaluation)

```bash
python3 scripts/reference_cli.py benchmark --mode pilot     # 5 prompts x 2
python3 scripts/reference_cli.py benchmark --mode full      # 192 x 2 (RC5.1 protocol)
python3 scripts/reference_cli.py compare --run-dir <run>    # scope-labelled comparison
```

Pilot scores are NEVER compared with the full scoreboard (the verify tool
classifies them VALID_PILOT_ONLY). Scoring (PER/SongBench/MuLan/AMC/Q3O)
follows `docs/BENCHMARK_REPRODUCTION.md`.

## What runs and what doesn't (gfx1100, upstream `c67d541a` native gates)

| Path | Status |
|---|---|
| AR decode (reference sampler, ATen flash attention) | works (validated vs eager: 0.0000 logit diff) |
| NAR (reference torch solver) | works |
| VAE fp32 tiled decode | works |
| DeepSelect fast sampler / fused decode+NAR (sgl_kernel) | CUDA-only — the author's native capability gates fall back to reference paths automatically |
| vLLM 0.19.1 ROCm (for the ASR evaluator arm) | works (with the disclosed platform-probe workaround) |
| vLLM 0.14.0 (official evaluator version) | no ROCm build exists — disclosed substitution |
| Q3O on 48 GB | RUNS (192/192, ROCm-adapted judge: 34 GPU + 14 CPU MoE layers); official CUDA equivalence NOT_ESTABLISHED |

## Troubleshooting quick index

- vLLM "Device string must not be empty" → amdsmi platform-probe failure;
  `rc5_asr_vllm_native.py` already contains the workaround.
- Q3O/ASR rc=139 in llvmlite during librosa import → numba kernels compile
  before torch loads (the judge and per-lab do this automatically).
- HTTP healthy but generation dead → `scripts/server_readiness.py check`.
- GPU busy → `python3 scripts/reference_cli.py status` shows the lock
  holder; `reference stop` sends a graceful stop.
- Full index: `docs/TROUBLESHOOTING.md`, boundaries:
  `docs/KNOWN_LIMITATIONS.md`, hardware: `docs/COMPATIBILITY_MATRIX.md`.

---

## Historical Reference (superseded paths — kept for traceability only)

- **ced0ef7d + patches 0001–0005/0008** (the pre-RC5 stack): the original
  verified path of the RC2–RC4 era. Superseded by the `c67d541a` frozen
  stack above; patches 0004/0005 were absorbed upstream and are NOT
  reapplied. Do not use for new runs.
- **Force-flag matrix** (`SGLANG_YUE2_*` env overrides): superseded by the
  upstream native capability gates (author's commit `2a816358d`).
- Old Q3O "NOT RUN on 48 GB" statements and RC4-era performance tables were
  superseded by the RC5.1 results; current numbers live in
  `reports/w7900_rc5/rc5_1/` and `reports/developer_reference/06_PERFORMANCE_REFERENCE.md`.
- `reports/gfx1100/PHASE*.md` remain the evidence for the historical path.
