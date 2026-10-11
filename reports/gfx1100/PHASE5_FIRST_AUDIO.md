# PHASE 5 — End-to-End Music Generation on W7900 (gfx1100)

**Status: PASS (GATE 5 met)** · Date: 2026-10-11/12
**Evidence:** `evidence/gfx1100/phase5_official.json` · raw audio retained locally (hashes in evidence)
**Launcher:** `scripts/serve_yue2_gfx1100.sh` (portable; env-flag matrix per Phase 4)

## 1. Server

`sglang serve` (PR #42106 @ ced0ef7d + patches 0001-0005/0008) on
`AMD Radeon Pro W7900D`, torch 2.12.0+rocm7.14.1, ROCm flag matrix
(FAST_SAMPLER/STEP_GRAPH/FUSED_DECODE/FAST_NAR/FA3/BATCHED_AR=0, SESSION=1).
Startup: pipeline + workers + FastAPI ready; `/health` → `{"status":"ok"}`.

## 2. Generations

| Test | Route | HTTP | Wall | Stages (server log) | Audio | Identity |
|---|---|---|---|---|---|---|
| smoke | `/v1/audio/generations` | 200 | 68.5 s | — | 24.0 s, rms .078 | (not finalized) |
| **official r0** (WSB p0, seed 831001) | `/v1/audio/generations` | 200 | 419.1 s | AR 147.0 / NAR 30.6 / VAE 241.5 | 185.88 s, rms .1666, peak 1.0 (1 sample) | `570c5ce90435fd1b…` |
| **official r1** (WSB p0, seed 831019) | `/v1/audio/music/generations` (alias) | 200 | 190.5 s | (log equivalents) | 146.00 s, rms .1647 | `cc34b973ec2fcad9…` |

Official parameters exactly: cot=full, effective cfg 1.0 (single-branch;
cfg_scale not sent — Yue2SamplingParams at head does not accept it),
ode_steps=32, semantic_max_tokens=9000, abc_max_tokens=4096,
vae_core_frames=1024, vae_halo_frames=16.

## 3. Validation checklist (all PASS)

48 kHz stereo; positive duration; finite (no NaN/Inf); non-zero RMS; no
serious clipping; decodes via soundfile; real GPU execution (rocm-smi 100%
utilization during stages, VRAM ≈ 11/48 GB during VAE); correct VAE identity
(weights_manifest verified via finalize); WAV hashes recorded
(r0 `fbe5a7b7…`, r1 `89c57566…`).

Official-schema bundles finalized with `scripts/finalize_candidate.py` and
**verified by the official frozen `wsb_metrics.artifact_storage.verify_result`**:
r0 status complete / truncated False / 4647 codec frames; r1 complete /
3650 frames.

## 4. Cross-machine identity check (noteworthy)

Both candidate identities are **byte-identical to the gfx1151 machine's pilot
identities for the same prompts/seeds** (see `evidence/pilot_manifest.jsonl`:
r0 `570c5ce9…`, r1 `cc34b973…`). The identity hashes request+config+weights,
so this proves the generation contract (request semantics, effective config,
weight verification) is exactly reproducible across the two AMD machines.
The audio itself differs across GPUs at equal seeds (185.9 s vs 162.3 s for
r0) — expected: GPU RNG/kernel math differs by architecture; the mission
explicitly waives cross-arch byte-identity.

## 5. Known telemetry gaps (recorded, not hidden)

The HTTP response reports `peak_memory_mb: 0.0` and null `yue2_stage_seconds`
on this stack (fields exist in the response schema but do not populate on the
ROCm path; likely an nvidia-smi-based probe). Stage timings were therefore
taken from the server log (authoritative stage instrumentation) and memory
from rocm-smi. Filed as a Phase 12/14 candidate (ROCm-compatible memory
reporting upstream contribution).

## 6. Gate 5 verdict

At least one true end-to-end output passes all checks; both HTTP routes
validated with official parameters; real GPU execution proved. **PASS.**
