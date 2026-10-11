# ROCm Compatibility Patches (gfx1151)

Each patch is minimal, documented, and independently applicable on top of the
pinned SGLang PR #42106 checkout (`ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`).
Apply with `git apply <patch>` from the sglang repository root.

## 0001-0003-aiter-import-guards.patch

**Original behavior:** Three modules under `sglang/srt/layers/quantization/`
import AMD's `aiter` package at module level whenever `torch.version.hip` is
set (`if _is_hip:`), assuming ROCm implies an Instinct CDNA GPU.

**Problem:** On gfx1151 (Radeon 8060S, RDNA4 APU) `aiter` does not exist — no
wheel is published for this architecture (verified against
repo.amd.com/rocm/whl-multi-arch and PyPI; PyPI's `aiter` is an unrelated 2019
project). Importing `sglang.srt.layers.quantization` therefore raises
`ModuleNotFoundError: No module named 'aiter'` and no model, including YuE2,
can load.

**Root cause:** architecture assumption ("HIP ⇒ aiter installable") baked into
module import order; upstream SGLang ROCm CI only exercises gfx94x/gfx95x
Instinct parts where aiter is present.

**Patch:** wrap the three offending import blocks in `try/except ImportError`,
binding the imported names to `None` on failure — mirroring exactly the
existing non-HIP fallbacks in the same files (`dynamic_mxfp4_quant = None`
etc.). Files touched:

1. `quark/schemes/quark_w4a4_mxfp4.py` (4 aiter imports + custom-op wrappers)
2. `quark/schemes/quark_w4a4_mxfp4_moe.py` (`dynamic_mxfp4_quant`)
3. `quark_int4fp8_moe.py` (`shuffle_weight`, `ON_GFX950` probe)

**Compatibility impact:** none on NVIDIA (guard is under `_is_hip`); none on
Instinct ROCm where aiter imports succeed unchanged.

**Accuracy risk:** zero for YuE2 (bf16, no Quark W4A4-MXFP4/Int4Fp8 quantized
layers, no MoE). If a Quark-quantized model were requested without aiter, the
registered custom ops fail at call time (loud `TypeError`) rather than at
import — strictly better diagnosability than today's import crash.

**Targeted test:** `tests/test_yue2_rocm_fallbacks.py::test_quantization_chain_imports`
import-success + symbol-is-None assertions (Phase 3 deliverable).
