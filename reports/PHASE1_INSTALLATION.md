# PHASE 1 — Reproducible ROCm 7.14.1 Environment

**Status: PASS**
**Date: 2026-10-11**

## 1. What was built

`scripts/setup_gfx1151.sh` (re-runnable, idempotent) builds `environments/yue2`
(Python 3.12.3, uv) containing:

| Component | Version | Source |
|---|---|---|
| torch | **2.12.0+rocm7.14.1** (HIP 7.14.60850) | repo.amd.com/rocm/whl-multi-arch, `torch[device-gfx1151]` |
| torchvision | 0.27.0+rocm7.14.1 | same |
| torchaudio | 2.11.0+rocm7.14.1 | same (matches sglang's own torchaudio pin) |
| triton | 3.8.0+git4cff872c.rocm7.14.1 | pulled by torch wheel (ROCm Triton) |
| sglang | 0.0.0.dev1+gced0ef7d1 (**editable, --no-deps**) | PR #42106 head checkout |
| transformers | 5.17.0 | PyPI (matches sglang pin) |

The AMD wheels bundle the ROCm 7.14.1 userspace, so the host's ROCm 7.2.1
userspace and in-tree kernel driver are untouched (mission rules 7/8).

## 2. The dependency conflict and how it was resolved

SGLang metadata pins `torch==2.14.1` (CUDA) plus CUDA-only packages
(`flashinfer_python[cu13]`, `sglang-kernel`, `aiter`-family, DeepEP/DeepGEMM,
CUDA python bindings). Installing with dependencies would have replaced the
ROCm torch with a CUDA torch — explicitly forbidden. Resolution:

1. `uv pip install --no-deps -e upstream/sglang/python`
   (`SGLANG_BUILD_RUST_EXTS=none`; cargo absent on host, documented).
2. Install SGLang's remaining dependency list **selectively**, skipping every
   NVIDIA-only package (full audit in `evidence/dependency_matrix.json`).
3. Auto-discovered additional runtime deps for the multimodal import chain:
   `imageio`, `imageio-ffmpeg`, `diffusers`, `addict`, `cache_dit`.

### Verification results

- `import torch` → 2.12.0+rocm7.14.1, HIP 7.14.60850, device AMD Radeon 8060S
- BF16 GPU matmul → finite, correct (setup script check)
- `import sglang` → ok
- `from sglang.srt.models.yue2 import modeling_yue2, modeling_vae` → ok
- `from sglang.multimodal_gen.runtime.pipelines import yue2_pipeline` → ok
- `uv pip check` → 17 incompatibilities, **all** attributable to the
  deliberately excluded CUDA-only packages; no ROCm-relevant conflict.

## 3. First ROCm compatibility findings (feeding Phase 3)

1. **aiter import crash (P1, fixed by patches 0001–0003).** Three
   quantization modules import `aiter` at module level under `if _is_hip:`.
   aiter has no gfx1151 build (verified: absent from AMD's multi-arch wheel
   index; PyPI `aiter` is an unrelated 2019 project). Import guards added,
   mirroring the existing non-HIP fallback (`= None`) in the same files.
   Accuracy risk for YuE2: zero (bf16 model, no Quark quant layers).
2. **sgl-kernel / flashinfer absent.** The PR's YuE2 fast paths (DeepSelect
   topk in `fastpath.py`, fused NAR in `nar_fast.py`) are built on
   sgl-kernel 0.4.7 + flashinfer 0.7.0.post — CUDA-only. ROCm must run the
   reference fallbacks (env-gated); Phase 3 verifies those fallbacks are
   complete and semantically correct, adding a tested graph-disable pathway
   if needed.
3. **Version drift note.** PR prose references sgl-kernel 0.4.7; pyproject at
   head pins sglang-kernel==0.4.9. Recorded; no action (neither installs on
   ROCm).

## 4. Model artifacts pinned and verified (downloads via hf-mirror.com)

| Artifact | Revision | SHA-256 | Official pin match |
|---|---|---|---|
| m-a-p/YuE2-3B model.safetensors | `1a96eca6…` | `1d55c42c…e59e9` | ✓ (code/generate.py MODEL_SHA) |
| m-a-p/YuE2-Vae-legacy model.safetensors | `b54118f0…` | `b6d28362…5044` | ✓ (VAE_SHA) |
| yue2_infer-0.1.3 wheel | `1a96eca6…` | `156d6b8b…4f07` | ✓ (install_inference.py assertion) |

## 5. Deliverables

- `scripts/setup_gfx1151.sh` — full environment build, re-runnable
- `evidence/dependency_matrix.json` — complete installed/excluded/audit table
- `patches/0001-0003-aiter-import-guards.patch` + `patches/README.md`
- `logs/phase1.log`, `logs/phase1_pipfreeze.txt`, `logs/model_hash_check.txt`
  (workspace, outside git)
- `reviews/PHASE1_REVIEW.md` (independent subagent)

## 6. Gate

**PASS** — torch/sglang import, BF16 GPU compute, and all YuE2 model modules
import cleanly in the isolated ROCm 7.14.1 environment; every deviation from
upstream metadata is documented in the dependency matrix.
