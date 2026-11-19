# YuE2 on AMD ROCm: Reproducing High-Quality Music Generation and Official Benchmarks on Radeon GPUs

**DRAFT v0.1 — 2026-11-19. NOT SUBMITTED for author/AMD review. Every number
below links to evidence; empty cells mean NOT_TESTED and stay that way.**

## What a Radeon developer achieves today (verified)

On a single AMD Radeon Pro W7900D (gfx1100, 48 GB) with ROCm, a developer
can today:

1. Run the **official YuE2 native PyTorch implementation** end-to-end
   (symbolic planning → semantic → acoustic → VAE decode) and generate
   complete songs (verified: full 384-candidate official benchmark campaign).
2. **Serve YuE2 with SGLang** on ROCm and drive full-song generation through
   an OpenAI-style audio API (verified: serving acceptance with a real
   33-second generation, identity-verified lifecycle).
3. Reproduce the **official WildSongBench** four-metric evaluation and get
   within ±0.03 SongBench / ±0.01 MuLan / ±0.01 AllMusicCaps of the
   published YuE2 reference (fresh native-implementation run).
4. Reuse the campaign tooling: single-GPU ownership lock, identity-verified
   server stop, crash-safe journals, strict artifact audits, per-candidate
   provenance chains — all open in this repository.

## Required environment (exact, receipted)

W7900D (gfx1100, 48 GB) · amdgpu 6.16.13 · host ROCm 7.2.1 userspace ·
per-env torch 2.12.0+rocm7.14.1 wheels · transformers 5.17.0 · pinned SGLang
source + ROCm compatibility patches 0001–0005/0008 · frozen WildSongBench
tree (manifest sha256 859e5225…) · ≥200 GB local storage.
Full matrix: `08_DEVELOPER_REPRODUCTION_GUIDE.md`.

## Your first complete song

Two paths, both receipt-verified on the fresh image:

```bash
# A. native official implementation (torch-eager)
bash scripts/campaign_ops/build_envA.sh && bash scripts/run_smoke_test.py …

# B. SGLang serving + real-audio acceptance
bash scripts/serve_yue2_gfx1100.sh
python scripts/campaign_ops/armb_acceptance_request.py --server http://127.0.0.1:31000 …
```

## Running the official benchmark (exactly)

192 prompts × 2 candidates, official seeds 831001+i/831019+i, 4-pass ASR
min, lower-PER selection, capped outputs retained, strict 384-candidate
audit, then solo four-metric scoring. Serialized by a mission chain that
refuses to advance without evidence gates (exit code AND complete summary AND
verdict-from-file). Reproduce: `08_DEVELOPER_REPRODUCTION_GUIDE.md` §4.

## Quality: what matches the author baseline — and what is still open

| Metric (selected-192) | Official | Native torch on W7900D | Status |
|---|---:|---:|---|
| SongBench GA ↑ | 6.7316 | 6.7044 | reproduces (Δ −0.027) |
| MuQ-MuLan ↑ | 0.5068 | 0.4970 | reproduces (Δ −0.010) |
| AllMusicCaps ↑ | 0.4054 | 0.4010 | reproduces (Δ −0.004) |
| PER ↓ | 8.44 % | 16.83 % | **open — under joint investigation** |
| Q3O ↑ | 4.6819 | (not run) | NOT_TESTED — official judge exceeds 48 GB |

The PER gap is **not** serving-specific: the authors' own implementation
shows the same offset on our hardware, identical uncapped PER across
different GPUs/stacks (16.15 % vs 16.14 %), deterministic ASR, and all
non-ASR judges reproduce. We present this transparently with the full causal
analysis and the cross-evaluator experiment designed to close it — no parity
is claimed that we cannot evidence. (Authors' collaboration request prepared.)

## Verified performance (to be completed after the running campaign)

| Quantity | Native torch | SGLang serving |
|---|---|---|
| Cold start / warm start | NOT_TESTED | NOT_TESTED |
| End-to-end full-song latency (P50/P95) | NOT_TESTED | NOT_TESTED |
| Real-time factor (definition explicit) | NOT_TESTED | NOT_TESTED |
| Peak VRAM / GTT | NOT_TESTED | NOT_TESTED |
| Concurrency C=1/2/4/8 | NOT_TESTED | NOT_TESTED |

(Filled from the M5 characterization in an uncontended window; no
cross-vendor speedup claims unless measurement conditions are genuinely
comparable.)

## Technical optimizations and compatibility fixes (the reusable part)

- ROCm import/capability guards for SGLang YuE2 (aiter/DeepSelect/fa3/
  kvcacheio) — patches 0001–0005/0008, chain-verified.
- Correctness-first serving flag matrix (documented per-flag rationale).
- Evaluator ROCm backend (Qwen3-ASR via transformers) + per-ROCM locking +
  reuse — patches 0006/0007/0009, disclosed in every score.
- `torch-eager` backend allowlist fix for the official evaluator (patch
  0010 — one line, no scoring-math change).
- Campaign reliability engineering: gpu ownership lock, verified-identity
  server stop (never pkill), crash-safe staged extraction, no-clobber
  archives, evidence-gated supervisor.

## Limitations (stated plainly)

1. PER parity is open (see above). 2. Q3O not run (judge memory). 3. AR-stage
hang (~1/300 historical) mitigated by watchdog, not root-caused. 4. Do not
share the GPU between evaluator and generator (known HIP fault class;
single-tenant policy enforced). 5. Native `close()` frees little device
memory in-process — fresh process per song is the supported pattern.
6. Historical git objects on old branches predate the current redaction
(current tree passes tier-2 scanning against the licensed dataset).

## What developers can reuse

The lock/identity/audit/journal/provenance tooling is model-agnostic and
MIT-compatible within this repo's license; the patch set generalizes to other
ROCm gfx1100-class deployments.

---
*Attribution: YuE2 by the m-a-p team; WildSongBench (research-use lyrics)
never republished here; evaluation under the authors' published protocol.
This draft has NOT been reviewed or endorsed by the YuE2 authors or AMD.*
