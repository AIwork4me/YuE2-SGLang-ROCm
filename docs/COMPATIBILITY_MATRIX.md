# Compatibility Matrix — YuE2 × SGLang PR #42106 × ROCm

Evidence-backed status per feature and platform. Sources: gfx1151 repo evidence
(phases 0-5, pilot), gfx1100 phases 0-7 (this branch), upstream PR text.
Legend: **TESTED PASS** / **TESTED FAIL** / **FALLBACK** (by design) /
**NOT TESTED**.

## Kernel path matrix

| Feature | gfx1151 (MAX+ 395, 8060S) | gfx1100 (W7900 48G) | H800 (upstream PR) |
|---|---|---|---|
| Reference AR (looped, pure torch sampler) | TESTED PASS | TESTED PASS | reference |
| GraphAR session graphs (HIP/CUDA graph + flash) | TESTED PASS | TESTED PASS (vs-eager max diff 0.0000) | enabled |
| Fast sampler (DeepSelect topk) | TESTED FAIL → FALLBACK | TESTED FAIL → FALLBACK (`is_deepselect_supported()`=False) | enabled |
| Fused decode (sgl_kernel) | ABSENT → FALLBACK | ABSENT → FALLBACK | enabled |
| Batched AR (BatchedGraphSampler) | GATED OFF → per-request AR | GATED OFF → per-request AR | enabled |
| Reference NAR (torch, SDPA) | TESTED PASS | TESTED PASS | reference |
| Fused NAR (sgl_kernel) | ABSENT → FALLBACK | ABSENT → FALLBACK | enabled |
| ATen native flash varlen (GQA, seqused_k) | TESTED PASS (~4e-3 vs fp32) | TESTED PASS (deterministic vs eager) | FA3 path used |
| Masked SDPA (MATH fallback) | TESTED PASS | TESTED PASS | — |
| cuDNN SDPA branch | no kernel on ROCm | NOT TESTED (never auto-selected) | available |
| VAE fp32 tiled decode | TESTED PASS | TESTED PASS | PASS |
| HIP graph capture/replay | TESTED PASS | TESTED PASS | CUDA graphs |
| Model load bf16 (YuE2-3B) | TESTED PASS | TESTED PASS | PASS |

## Package availability

| Package | gfx1151 | gfx1100 | Note |
|---|---|---|---|
| torch 2.12.0+rocm7.14.1 (AMD index) | yes | yes | mission-pinned |
| aiter | no build | no build | Instinct CDNA only; patches 0001-0003 |
| sgl_kernel | no build | no build (PyPI = CUDA sm100) | fallbacks + patch 0008 |
| flashinfer | CUDA-only flavors | CUDA-only flavors | not needed on YuE2 ROCm path |
| vllm (evaluator PER) | no (0.14.0 CUDA-only) | 0.19.1 ROCm works (E2 PER arm, disclosed engine substitution) | patch 0007: transformers ASR backend for the frozen arm; vLLM 0.14.0 has no ROCm build |
| flash_attn 2.8.3 (Q3O) | no | no (HF SDPA used instead) | Q3O runs via the ROCm-adapted judge (see below) |

## Reproduction identity

| Property | gfx1151 | gfx1100 |
|---|---|---|
| SGLang commit | ced0ef7d (PR #42106 head) | same |
| Patches | 0001-0005 | 0001-0005 + 0008 (0008 needed because the serving import chain reaches kvcacheio modules on this stack) |
| Models / dataset | pinned, SHA256-verified | same pins, re-verified |
| torch | 2.12.0+rocm7.14.1 | same |
| Candidate identity (request+config+weights hash) | 570c5ce9…/cc34b973… (pilot p0) | **byte-identical** |
| Audio at equal seeds | differs (arch-dependent GPU math/RNG) | differs (185.9 s vs 162.3 s @ p0 r0) — expected, not a bug |

## Known gaps on ROCm (both AMD targets)

- `peak_memory_mb: 0.0` / null stage fields in HTTP response (nvidia-smi-based
  probe absent) — memory truth via rocm-smi; stage timings via server log.
- No DeepSelect/sgl_kernel acceleration ⇒ AR decode uses the reference sampler
  (correctness-first; performance cost quantified in PERFORMANCE_BASELINE).


## 2026-11-12 verification (publication-readiness mission, W7900D gfx1100)

| Capability | Status | Evidence |
|---|---|---|
| torch 2.10.0+rocm7.1 wheel on gfx1100 (matmul, SDPA) | PASS | phase-0 smoke + Arm A pilot |
| official yue2-infer 0.1.3 `--backend torch-eager` full song | PASS | evidence/publication/armA_pilot (2/2) |
| official frozen evaluator PER scoring on ROCm (patches 0006/0007/0009/0010) | PASS | evidence/publication/armA_pilot/per_song.jsonl |
| SGLang #42106 @ ced0ef7d + patches 0001-0005/0008 server | PASS | /health + generation smoke, 48 kHz stereo artifacts |
| Arm B full 384-candidate campaign (fresh, this tree) | IN PROGRESS | evidence/publication/armB_campaign/progress.jsonl |
| pip build isolation pulls CUDA torch for editable sglang | HAZARD (mitigated: --no-build-isolation) | RCA-3 |
| plain (no device-extra) AMD torch wheels on gfx1100 | FAIL (hipErrorInvalidImage) — use [device-gfx1100] | TROUBLESHOOTING |

## RC5.1 / RC6 status (current — W7900D gfx1100, upstream c67d541a)

| GPU / platform | Generation | PER (both arms) | SongBench/MuLan/AMC | Q3O | Overall status |
|---|---|---|---|---|---|
| W7900 / W7900D 48 GiB (gfx1100) | PHYSICAL_PASS 384/384 | PHYSICAL_PASS (transformers frozen + vLLM corrected arms) | PHYSICAL_PASS 192/192 selected | PHYSICAL_PASS ROCm-adapted 192/192 (official equivalence NOT_ESTABLISHED) | **PHYSICAL_PASS** |
| Radeon 8060S 32 GiB (gfx1151) | PARTIAL_PHYSICAL_PASS (historical pilot-era evidence, ced0ef7d stack) | NOT TESTED on the c67d541a stack | NOT TESTED | NOT RUN | PARTIAL_PHYSICAL_PASS (historical only) |
| RX 7900 XTX (gfx1100, 24 GiB) | EXPECTED_BUT_UNVERIFIED (same arch; VRAM budget tighter for Q3O) | EXPECTED_BUT_UNVERIFIED | EXPECTED_BUT_UNVERIFIED | NOT_TESTED (48 GiB was required; 24 GiB below the measured 42.4 GiB judge peak) | EXPECTED_BUT_UNVERIFIED |
| RX 9070 XT (gfx1200) | EXPECTED_BUT_UNVERIFIED (no torch wheel tested here) | EXPECTED_BUT_UNVERIFIED | EXPECTED_BUT_UNVERIFIED | NOT_TESTED | EXPECTED_BUT_UNVERIFIED |
| Other Radeon / CDNA (MI300…) | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED |

Statuses per the RC6 vocabulary: PHYSICAL_PASS / PARTIAL_PHYSICAL_PASS /
EXPECTED_BUT_UNVERIFIED / NOT_TESTED / UNSUPPORTED. Same-arch ≠ verified:
the W7900 results do NOT automatically extend to other Radeon cards.
Q3O peak VRAM on 48 GiB: 42.41 GiB torch-allocated (see
`reports/developer_reference/06_PERFORMANCE_REFERENCE.md`).
