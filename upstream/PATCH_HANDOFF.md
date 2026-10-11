# Patch Handoff — SGLang PR #42106 on AMD ROCm

Two independent patch series, both minimal and separately applicable on top
of `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`.

## Series A — SGLang (`patches/0001-0005-rocm-compat.patch`)

| # | File | Change | NVIDIA impact | Instinct impact | Accuracy risk |
|---|---|---|---|---|---|
| 0001 | `srt/layers/quantization/quark/schemes/quark_w4a4_mxfp4.py` | aiter imports under try/except → `None` | none (guard under `_is_hip`) | none (imports succeed) | zero for YuE2; loud TypeError if Quark W4A4 requested without aiter |
| 0002 | `…/quark_w4a4_mxfp4_moe.py` | `dynamic_mxfp4_quant` → `None` fallback | none | none | zero |
| 0003 | `…/quark_int4fp8_moe.py` | `shuffle_weight` + `ON_GFX950` guard | none | none | zero |
| 0004 | `srt/models/yue2/fastpath.py`, `song.py`, `batched.py` | DeepSelect gated on `is_deepselect_supported()` | none (helper True on SM 9/10) | none | zero — selects the PR's own reference paths |
| 0005 | `srt/models/yue2/fa3.py` | shared varlen wrapper call wrapped; fall through to ATen native | none (except never taken) | none | zero on CUDA; ROCm path numerically validated |

Not patched (auto-fallbacks verified): `cuda_graph.py` fused decode
(sgl_kernel try/except), `nar_fast.py` lazy `_sgl_kernel`, GraphAR attention
auto→flash on ROCm.

Suggested upstream split, smallest-first: 0001–0003 (platform guards);
0004 (correctness gate — recommended regardless of ROCm, since
importable-but-unrunnable is a latent H100-class footgun only when kernels
are missing); 0005 (call-time fallback).

## Series B — WSB evaluator (`patches/0006-0007-wsb-evaluator-rocm.patch`)

Not for upstream SGLang; scoped to the WildSongBench evaluator bundle.
`verify_environment` gains an env-gated torch-family exemption with receipt
recording; the PER scorer gains a transformers-backend ASR branch under the
same gate. `release.json` hashes updated openly. Full analysis, parity risks
and the same-audio evidence: `patches/EVALUATOR_PATCH_AUDIT.md`.
Equivalence with the CUDA/vLLM evaluator is **not claimed**.

## Verification entry points

- `tests/test_yue2_rocm_fallbacks.py` — 10 tests incl. real-model
  GraphAR-vs-eager logits and attention numerics (Phase 3 gate).
- `tests/test_verify_wsb_artifacts.py` — 12 auditor tests incl. the
  subset-cannot-pass-full-mode proof.
- `tests/test_first_audio.py` — HTTP-path audio validation.
- Evidence repo: every phase report paired with an independent review file.
