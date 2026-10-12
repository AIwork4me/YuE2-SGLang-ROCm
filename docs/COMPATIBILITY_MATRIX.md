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
| vllm (evaluator PER) | no (0.14.0 CUDA-only) | no | patch 0007: transformers ASR backend |
| flash_attn 2.8.3 (Q3O) | no | no | Q3O NOT RUN |

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
