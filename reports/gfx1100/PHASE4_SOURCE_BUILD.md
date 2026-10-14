# PHASE 4 — SGLang from Source on ROCm gfx1100

**Status: PASS (GATE 4 met)** · Date: 2026-10-11
**Evidence:** `evidence/gfx1100/compatibility_tests.json`, `evidence/gfx1100/phase4_compat_tests.log`, `evidence/gfx1100/dependency_receipt_gfx1100.json`

## 1. Build/install strategy (no CUDA substitutions)

1. Source: codeload tarball of PR #42106 head `ced0ef7d` → git-inited locally
   (`27ee2a2` pristine, `ff367ee` patches 0001–0005, `f00d9fc` patch 0008).
2. `git apply --check` on the gfx1151 patch series: **applies clean** on the
   pinned source; every hunk reviewed (identical files, no upstream drift — PR
   head unchanged since 2026-10-04).
3. Install: `SGLANG_BUILD_RUST_EXTS=none pip install --no-deps
   --no-build-isolation -e upstream/sglang/python`.
   - `--no-build-isolation` is REQUIRED: pyproject `build-system.requires`
     pins `torch==2.14.1` (CUDA), which would be downloaded into the build env
     and violate the no-CUDA rule. Skipping isolation uses the venv's own
     setuptools (setuptools-scm installed explicitly).
   - Rust extensions skipped (not used by the YuE2 HTTP serving path; matches
     gfx1151 precedent).
4. Runtime dependency set assembled by iterative import resolution against the
   actual serving chain (`sglang serve` CLI), recording every addition
   (receipt in evidence). Torch protected by a constraints file — any conflict
   would fail loudly. No nvidia-*/cuda-* package installed at any point
   (`pip freeze` audit). One mistake (deploop auto-installing PyPI's CUDA-only
   `sgl-kernel` sm100 wheel) was caught by the import probe and **uninstalled**;
   recorded as a cautionary note in the receipt.

## 2. New patch 0008 (gfx1100 addition to the ROCm series)

The serving import chain on this stack reaches three modules that import
`sgl_kernel.kvcacheio` at module level under `is_hip()`
(`mem_cache/hisparse_memory_pool.py`, `mem_cache/memory_pool_host.py`,
`mem_cache/pool_host/mha.py`). No ROCm sgl_kernel build exists for gfx1100/gfx1151,
so the import crashed unrelated model loading. Patch 0008 wraps these in
try/except ImportError binding to loud call-time stubs — the same shape the
files already use for non-CUDA backends. HiSparse/host-KV-transfer remains an
opt-in feature no YuE2 path touches.

## 3. Hardware capability matrix (independently probed on W7900)

| Feature | gfx1151 (prior) | gfx1100 (this run) | H800 upstream |
|---|---|---|---|
| Reference AR (GraphAR flash/ATen) | PASS | **TESTED PASS** (graph-vs-eager max\|diff\| 0.0000 / 0.0000, logit scale 33.75) | reference |
| GraphAR capture/replay (HIP graphs) | PASS | **TESTED PASS** | CUDA graphs |
| Fast sampler (DeepSelect) | FAIL→fallback | **TESTED FAIL→fallback** (`is_deepselect_supported()` False; gate enforced) | enabled |
| Fused decode (sgl_kernel) | absent→fallback | **ABSENT→fallback** | enabled |
| Batched AR | OFF (gate) | **TESTED OFF** (gate; env + capability) | enabled |
| Reference NAR | PASS | **TESTED PASS** (fp32 latents finite) | reference |
| Fused NAR (sgl_kernel) | absent→fallback | **ABSENT→fallback** | enabled |
| ATen flash varlen+GQA+seqused_k | PASS (≈4e-3) | **TESTED PASS** (<0.02 tol; deterministic vs eager) | FA3 |
| Masked SDPA (MATH) | PASS | **TESTED PASS** | — |
| VAE fp32 tiled | PASS | **TESTED PASS** | PASS |

No gfx1151 result was copied as evidence: every row above was re-executed on
W7900 (`tests/test_yue2_rocm_fallbacks.py`, now machine-portable via
`YUE2_WORKSPACE`).

## 4. Import/verification gate

`tests/test_yue2_rocm_fallbacks.py` — **11/11 PASSED** (30.8 s), including
`test_kvcacheio_import_guards` (new, patch 0008) and the real-model tests
(YuE2-3B bf16 on device). `sglang serve --help` exits 0.

## 5. Deviations from the gfx1151 environment

- transformers 5.17.0 / tokenizers 0.23.2 / compressed-tensors 0.18.0 /
  openai 2.6.1 / sentencepiece 0.2.1 pinned to match both the upstream pin and
  the gfx1151 receipt; numpy 2.4.4 (AMD-wheel-provided) vs gfx1151's 2.3.5 —
  recorded, no functional impact observed in the test gate.
- Environment flags for serving: identical matrix to gfx1151
  (`SGLANG_YUE2_FAST_SAMPLER=0, STEP_GRAPH=0, FUSED_DECODE=0, FAST_NAR=0,
  FA3=0, BATCHED_AR=0, SESSION=1, GRAPH_POOL=1`) — see the launcher.

## 6. Gate 4 verdict

All relevant import and unit tests pass; the real model loads and executes
AR/NAR/VAE paths on gfx1100 with finite outputs. **PASS.**
