# SGLang Patch Handoff (upstream-ready, DRAFT — not submitted)

Prepared for the SGLang maintainers of PR #42106 (and main). Every patch below
is small, architecture-agnostic, and validated on two independent AMD platforms
(gfx1151 Ryzen AI MAX+ 395 and gfx1100 Radeon PRO W7900, torch
2.12.0+rocm7.14.1) with the NVIDIA path untouched (guards only trigger where
the import would otherwise crash).

Patches apply on the PR head `ced0ef7d`; applicability against current `main`
re-verified 2026-10-12 (aiter and kvcacheio import sites unchanged there).

## Series (ordered by merge likelihood)

### 1. quark aiter import guards (patches 0001-0003)
- **Problem**: `if _is_hip: from aiter...` module-level imports in
  `quark/schemes/quark_w4a4_mxfp4.py`, `quark_w4a4_mxfp4_moe.py`,
  `quark_int4fp8_moe.py` crash with ModuleNotFoundError on any HIP device
  without aiter (all RDNA/Radeon parts; aiter ships for Instinct CDNA only).
  This blocks importing ANY model, not just Quark-quantized ones.
- **Fix**: try/except ImportError binding to the files' existing non-HIP
  fallback shapes (`None`), so the ops raise a loud, clear error only if a
  Quark W4A4 model is actually requested.
- **Accuracy/perf impact**: none (YuE2 and all bf16 models never call these
  ops; on Instinct the imports succeed unchanged).
- **Tests**: `test_quantization_chain_imports` (gfx1151 + gfx1100 evidence).
- **Regression risk**: minimal; mirrors existing fallback structure in-file.

### 2. sgl_kernel.kvcacheio import guards (patch 0008)
- **Problem**: `mem_cache/hisparse_memory_pool.py`,
  `mem_cache/memory_pool_host.py`, `mem_cache/pool_host/mha.py` import
  `sgl_kernel.kvcacheio` at module level under `_is_hip` — assuming ROCm
  sgl_kernel builds exist. None do for RDNA targets, so `sglang serve` dies on
  import before loading any model.
- **Fix**: same guard pattern; names bind to a stub raising RuntimeError with
  the missing-dependency context at call time. HiSparse/host-KV transfer is
  opt-in and untouched functionally.
- **Tests**: `test_kvcacheio_import_guards` + `sglang serve --help` rc=0
  (gfx1100 evidence `compatibility_tests.json`).
- **Note**: PyPI `sgl-kernel` on ROCm additionally misclassifies gfx
  capability 11.0 as "SM110" and demands CUDA libnvrtc — worth a loud
  "no ROCm build" error message in sgl_kernel's loader (separate issue).

### 3. DeepSelect capability gating (patch 0004)
- **Problem**: `fastpath.fast_sampler_available()` equated "wrapper imports +
  torch.cuda.is_available()" with "kernel runnable". On ROCm the wrapper
  imports but its CUDA JIT kernel cannot run; failure surfaces mid-decode or
  inside graph capture, killing requests instead of falling back.
- **Fix**: consult the tree's own `is_deepselect_supported()` (already
  correct: `torch.version.cuda is None` → False) at selection time; also gate
  `song.py` step-graph entry and `batched.batched_ar_enabled()`.
- **Impact**: unsupported devices select the shipped reference paths (looped
  AR + reference sampler). Supported CUDA GPUs: behavior identical.
- **Tests**: `test_deepselect_fallback`; full 11/11 suite green on both AMD
  targets.

### 4. FA wrapper call-time fallback (patch 0005)
- **Problem**: `yue2/fa3.varlen_attention` falls back to native ATen flash
  only when the shared wrapper IMPORT fails; on ROCm the import succeeds and
  the call fails (missing FA2 `flash_attn`).
- **Fix**: try/except around the call, falling through to
  `torch.ops.aten._flash_attention_forward`.
- **Validation**: varlen+GQA+seqused_k bf16 numerics vs fp32 manual reference
  (<0.02 tol; gfx1100: deterministic 0.0000 vs eager logits on real weights).

## Suggested PR split
1+2 are generic portability guards (srt/layers + srt/mem_cache; broadly
useful beyond YuE2). 3+4 are YuE2-path robustness (models/yue2). We suggest
two PRs along that seam, or one per the maintainers' preference.

## Non-patch findings (issues/notes only)
- HTTP response `peak_memory_mb` reports 0.0 on ROCm (nvidia-smi-based
  probe); stage telemetry fields null. Suggest pynvml→generic probe swap.
- `pyproject build-system.requires` pins CUDA torch, forcing ROCm source
  builds to use `--no-build-isolation`; a ROCm-aware build extra would help.

(No public submission of any of the above without owner approval per mission
policy; this document is the handoff package.)
