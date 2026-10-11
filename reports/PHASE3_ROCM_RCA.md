# PHASE 3 — ROCm Compatibility Root-Cause Analysis

**Status: PASS — AR, NAR and VAE each execute on gfx1151 with finite outputs (gate met; see §6)**
**Date: 2026-10-11**

## 1. Method

Read the complete YuE2 implementation in the PR checkout (~4.8k lines:
modeling, song, sampling, fastpath, cuda_graph, fa3, nar, nar_fast,
streaming, storage, protocol, batched, pipeline stages, loader, HTTP
entrypoints, the PR's own E2E test), enumerated every platform-conditional
(`_is_hip`, `device.type == "cuda"`, CUDA-only imports), then probed each
doubtful primitive **empirically on the actual gfx1151 + torch
2.12.0+rocm7.14.1 stack** before deciding to patch or rely on an existing
fallback. Correctness first: every patched or fallback path is locked by a
test in `tests/test_yue2_rocm_fallbacks.py`.

## 2. Platform-primitive probe results (gfx1151)

| Primitive | Result |
|---|---|
| `torch.backends.cudnn.is_available()` | True (MIOgen-backed) |
| `SDPBackend.CUDNN_ATTENTION` | **RuntimeError: No available kernel** (cuDNN attention not built for ROCm) |
| `SDPBackend.FLASH_ATTENTION` / `EFFICIENT_ATTENTION` (with mask/GQA) | **No available kernel** |
| `SDPBackend.MATH` | OK (correct; the effective GraphAR-`sdpa` backend) |
| `torch.ops.aten._flash_attention_forward` | **present with `seqused_k` schema; executes varlen+GQA bf16; matches fp32 manual reference max\|diff\| ≈ 4e-3** |
| `torch.cuda.CUDAGraph` capture + replay (HIP graphs) | **works** (validated semantics) |
| `sglang.kernels.ops.deep_select` (in-tree) | imports, but CUDA-only JIT (SM 9.0/10.0/10.3); `topk()` would raise at call time on gfx1151 |
| `sglang.kernels.ops.attention...flash_attn_varlen_func` | imports; at call time needs `flash_attn` (absent) → fails |

Consequences: GraphAR `attention_backend="auto"` resolves to **"flash"** on
this stack (ATen op present), so the broken cuDNN branch is never selected;
HIP graph capture is usable; the two real hazards were DeepSelect
(importable-but-unrunnable) and the shared FA wrapper (importable, fails at
call time) — both patched (0004, 0005).

## 3. Issues found and resolutions

| # | Component | Original behavior | Problem on gfx1151 | Root cause | Fix | Accuracy risk |
|---|---|---|---|---|---|---|
| 1 | quantization chain (3 files) | `if _is_hip: from aiter...` | ModuleNotFoundError at import; no model loads | aiter ships only for CDNA Instinct | patches 0001–0003 (import guards → None, matching the files' own non-HIP fallbacks) | zero for YuE2 (bf16, no Quark quant) |
| 2 | `fastpath.fast_sampler_available`, `song.py` step-graph gate | importable backend ∧ cuda available | FastSampler constructed / step-graph entered; `topk()` raises mid-decode / during graph capture | importability ≠ runnability; own `is_deepselect_supported()` never consulted | patch 0004: consult `is_deepselect_supported()` | zero (selects the PR's reference sampler; no math change) |
| 3 | `fa3.varlen_attention` | shared wrapper when importable; ATen only if import fails | wrapper imports, fails at call time (no `flash_attn`) | import/call split | patch 0005: try/except at call → ATen native (numerics validated) | zero on CUDA (except never taken) |
| 4 | `cuda_graph.py` fused decode | `import sgl_kernel` try/except | sgl_kernel absent | no ROCm wheel | **no patch needed**: falls back to reference `_decode` automatically | zero |
| 5 | `nar_fast.py` fused NAR | `_sgl_kernel()` lazy | sgl_kernel absent | same | **no patch needed**: stage catches and runs reference `nar.synthesize` (pure torch, sdpa) | zero |
| 6 | GraphAR `sdpa`/`cudnn` branches | sdpa_kernel contexts | MATH-only on ROCm; cudnn branch would crash | ROCm SDPA backends | not auto-selected (flash wins); `sdpa` path correct via MATH; **Phase 9** perf candidate | zero (correctness) |
| 7 | NAR/reference attention | SDPA | falls to MATH | same as 6 | acceptable (correct); benchmark uses reference NAR anyway | zero |

Nothing in sampling math, tokenization, seeds, ODE algorithm, or model
architecture was modified. The full working-tree diff (6 files, +66/−15) is
`patches/0001-0005-rocm-compat.patch`.

## 4. Environment-flag matrix for the ROCm run

Explicitly set for determinism in our server launcher (the patches make the
code correct without them; flags document intent):

| Flag | Value | Why |
|---|---|---|
| `SGLANG_YUE2_FAST_SAMPLER` | 0 | DeepSelect unavailable (patch 0004 also enforces) |
| `SGLANG_YUE2_STEP_GRAPH` | 0 | fused decode+sample graph needs DeepSelect |
| `SGLANG_YUE2_FUSED_DECODE` | 0 | sgl_kernel absent |
| `SGLANG_YUE2_FAST_NAR` | 0 | fused NAR needs sgl_kernel |
| `SGLANG_YUE2_SESSION` | 1 | **kept on**: session GraphAR works on ROCm (HIP graphs + ATen flash); looped sampling uses the reference sampler |
| `SGLANG_YUE2_FA3` | 0 | skip shared wrapper; ATen native (validated) — patch 0005 also covers flag-on |
| `SGLANG_YUE2_BATCHED_AR` | 0 | BatchedGraphSampler needs DeepSelect |

## 5. Validation of semantics (mission checklist)

- **attention masks**: bool-mask semantics (True=allowed) verified against a
  hand-built reference (`test_masked_sdpa_math_fallback`); GraphAR's
  `visible = key_positions <= positions` construction reviewed line-by-line.
- **causal/non-causal**: NAR prefill uses `causal=True` with block-wise
  absolute-position masks (reviewed); AR decode uses non-causal attention over
  the visible prefix (`seqused_k` caps each row).
- **GQA semantics**: 8:2 head pattern validated numerically for both the ATen
  flash op and masked SDPA.
- **effective sequence lengths**: `seqused_k` honored per row (validated with
  kv=5 vs 16 rows in one call).
- **numerical stability**: finite outputs asserted everywhere; AR logits
  GraphAR-vs-eager within tolerance (below).
- **output tensor shapes**: asserted in every test.
- **KV cache behavior**: GraphAR scatter into fixed slots + reopen() reuse
  reviewed; `test_ar_graph_vs_eager_logits` compares cached decode logits
  against a fresh StaticKVCache eager run — max|diff| < 0.05 × logit scale
  (bf16 attention noise level), both for prefill and step.

## 6. Gate evidence

`tests/test_yue2_rocm_fallbacks.py` — **10/10 passed** on gfx1151:

```
test_quantization_chain_imports           PASS  (patches 0001-0003)
test_deepselect_fallback                  PASS  (patch 0004)
test_aten_flash_varlen_numerics           PASS  (max|diff| ≈ 4e-3 vs fp32 ref)
test_masked_sdpa_math_fallback            PASS
test_hip_graph_capture_replay             PASS
test_model_loads_on_gfx1151               PASS  (YuE2-3B bf16 on GPU)
test_ar_graph_vs_eager_logits             PASS  (prefill & step, flash backend)
test_reference_sampler_distribution_...   PASS  (mask semantics at full vocab)
test_nar_solver_finite                    PASS  (reference NAR, 2-step probe)
test_vae_decode_finite                    PASS  (tiled fp32 decode)
```

Raw run: `python -m pytest tests/test_yue2_rocm_fallbacks.py -q` →
`10 passed`. Machine-readable summary: `evidence/compatibility_tests.json`.

**Gate: AR, NAR and VAE each execute independently on gfx1151 with finite
outputs → PASS.**

## 7. Deliverables

- `patches/0001-0005-rocm-compat.patch` + `patches/README.md` (per-hunk RCA)
- `tests/test_yue2_rocm_fallbacks.py`
- `evidence/compatibility_tests.json`
- this report; `reviews/PHASE3_REVIEW.md` (independent subagent)
