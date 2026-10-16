# 05 — Omni regression results (unit + semantic + physical GPU)

Environment: env-omni-rocm (Python 3.12.3, torch 2.12.0+rocm7.14.1,
transformers 5.12.1, pytest 9.1.1), PYTHONPATH-shadowed worktree (validated
editable env untouched).

## Unit tests

| Suite | Base ae11c6ad | Closure b91b95440 |
|---|---|---|
| test_yue2_platform_gates.py (CUDA/ROCm dispatch gates, mocked platform) | 12 pass | 12 pass |
| test_yue2_speech_input_cap.py (API input contract + other TTS defaults) | 13 pass | 13 pass |
| test_model_capabilities.py (model registration/capabilities) | 37 pass | 37 pass |
| test_yue2_rename_regression.py (NEW — 14 tests) | n/a | **14 pass** |
| **Total** | 62 | **76** |

New regression tests pin: public names exist / old names gone at module and
class surface; cross-file lazy loaders import (song → fastpath/sampling);
pool/lease attribute behavior incl. refcount release; model fused-weight
cache attribute round-trip (yue2_fused_weights / yue2_fused_nar_weights);
`RotaryEmbedding.state_dict() == []` after forward (checkpoint stability);
`YuE2Config`/`YuE2VAEConfig` `to_dict()` excludes the field-set names and
keeps inference fields (serialization stability); tokenizer/VAE/NAR/song
public surface.

## Semantic audit (identifier-only proof)

AST-level: for all 12 changed sources, base source transformed by exactly
the rename map is `ast.dump`-EQUAL to the closure tree (song.py: one
from-import member reorder per isort; tests: exactly the 2 setattr strings;
MIGRATION.md: 1 doc line; plus the new test file). Token-stream cross-check
by an independent reviewer: the only changed tokens are NAME→NAME under one
consistent map plus the two paired getattr cache-key strings
(`"yue2_fused_weights"`/`"yue2_fused_nar_weights"`, required to stay
coherent with the attribute renames). No NUMBER/OP/keyword/logic-string
changes. Full detail: `SEMANTIC_REGRESSION_AUDIT.md`.

## Physical GPU validation (AMD Radeon Pro W7900D, ROCm, NOT a benchmark)

Same known-good seeded short request as the 2026-10-13 validated smoke
(style/lyrics, cot=full, seed 20261013, 128/300/4), POST /v1/audio/speech,
server `sgl-omni serve --model-path YuE2-3B`, PYTHONPATH-shadowed source:

| Tree | Result |
|---|---|
| ae11c6ad (old names) | HTTP 200; WAV 48 kHz stereo 12.00 s; rms 0.0963, peak 0.795; 0 errors |
| b91b95440 (renamed) | HTTP 200; WAV 48 kHz stereo 12.00 s; rms 0.0963, peak 0.795; 0 renamed-symbol errors |

**The two WAV files are BIT-IDENTICAL (sha256
8144825a8eed8aa1533ad30f9826b1fbeb412ec9cb12e39cda2c106e3674797f).**
The rename provably changed zero runtime behavior on the physical ROCm
reference path (AR looped generator → CachedNAR reference ODE → VAE decode).
Artifacts: smoke-out-base/, smoke-out-renamed/ (manifest, server.log, wav).

Mocked-platform gate tests remain mocked tests; the physical H800/CUDA fast
path is NOT covered here (see report 08).
