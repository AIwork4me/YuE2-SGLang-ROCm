# PHASE 4 — First Real End-to-End Music Generation

**Status: PASS — real audio generated on gfx1151 through the SGLang HTTP path**
**Date: 2026-10-11**

## 1. Setup

Server launched with `scripts/serve_yue2_rocm.sh`: `sglang serve
--model-path models/YuE2-3B --num-gpus 1 --ulysses-degree 1 --ring-degree 1
--warmup-mode off`, VAE = `models/YuE2-Vae-legacy` (benchmark decoder), ROCm
flag matrix from Phase 3 (`FAST_SAMPLER/STEP_GRAPH/FUSED_DECODE/FAST_NAR/
FA3/BATCHED_AR = 0`, `SESSION = 1`). No fake fixtures anywhere: every file
below came from the live HTTP endpoint on the Radeon 8060S.

## 2. Requests and results

| Request | Budget (ode/sem/abc/vae) | HTTP | Wall | Audio |
|---|---|---|---|---|
| smoke1 (cot=full) | 8 / 300 / 256 / 256f | 200 | 64.3 s | 12.0 s valid WAV |
| **full1 (cot=full, official)** | **32 / 9000 / 4096 / 1024f+16h** | **200** | **337.9 s** | **68.76 s** |
| full1_repeat (same seed) | same | 200 | 134.6 s (warm) | byte-identical |
| alias1 (`/v1/audio/music/generations`) | 4 / 100 / 128 / 256f | 200 | 21.2 s | 4.0 s valid |

full1 internals (from its artifact `plan.json`): 607 ABC tokens, 1720 codec
tokens, not truncated; ABC phase 20.7 s, semantic phase 82.3 s; sampler
`reference`, execution `cuda_graph`, attention `flash` — i.e. the ROCm path
runs the PR's session GraphAR with the native ATen flash op and the pure-torch
reference sampler, exactly as designed in Phase 3.

## 3. Success checks (mission list)

- HTTP success status: ✓ (200 on both routes)
- Output file exists: ✓ `runs/phase4/*.wav`
- Decodable WAV: ✓ (soundfile)
- Sample rate: ✓ 48000
- Two channels: ✓
- Positive duration: ✓ (4.0–68.76 s)
- Non-zero RMS: ✓ (0.051–0.109)
- No NaN/Inf: ✓
- No serious clipping: ✓ (clip fraction 0.0, peaks ≤ 0.71)
- GPU execution confirmed: ✓ (attention=flash on cuda:0; AR via HIP-captured
  decode graph; artifacts' timing blocks record backends)
- Peak memory: GTT used after generation 11.6 GiB of 107 GiB (rocm-smi).
  Caveat: the response's `peak_memory_mb` field returns 0.0 — not wired for
  this pipeline in the PR build (upstream gap, documented; the Phase 6 driver
  adds its own per-candidate memory polling).
- Stage timing: ✓ (above; NAR+VAE ≈ remaining ~235 s of full1 wall — the
  reference-NAR MATH-SDPA path is the dominant cost; Phase 9 target)

## 4. Same-seed behavior

The repeat request produced a **byte-identical WAV** (sha256 match, same
duration). Same-seed identity was not a pass requirement (the PR itself notes
H800 split-K atomics can flip near-boundary samples), but the ROCm
configuration (reference sampler + ATen flash + MATH SDPA) is deterministic
here. Recorded as an observation about our stack, not a general claim.

## 5. Artifacts

`runs/phase4/full1_artifacts/` contains the WSB-style bundle
(latent/semantic/prefix/abc_tokens .npy + plan.json + plan_manifest.json +
request.json) produced by the PR's `export_song_artifacts`. Audio + artifacts
stay outside git; hashes in `evidence/first_audio.sha256`, metadata in
`evidence/first_audio_metadata.json`.

## 6. Deliverables

- `reports/PHASE4_FIRST_AUDIO.md` (this file)
- `evidence/first_audio_metadata.json`, `evidence/first_audio.sha256`
- `tests/test_first_audio.py` (6/6 pass against the real files)
- `scripts/serve_yue2_rocm.sh`
- `reviews/PHASE4_REVIEW.md` (independent subagent)

## 7. Gate

**PASS** — AR, NAR, VAE and the full AR→NAR→VAE chain run through the
SGLang HTTP endpoint on gfx1151 with valid, non-silent, unclipped 48 kHz
stereo audio; both routes work; same-seed repeat succeeds.
