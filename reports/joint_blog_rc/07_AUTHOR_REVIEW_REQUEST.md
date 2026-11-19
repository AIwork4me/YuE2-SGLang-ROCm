# 07 — YuE2 author review request (concise, sendable)

**To:** YuE2 team (m-a-p / multimodal-art-projection) · **From:** AIwork4me
(YuE2-SGLang-ROCm) · **Date:** 2026-11-19 · **Re:** joint AMD ROCm technical
blog — scientific parity items requiring author input

Dear YuE2 authors,

We have completed a fresh, fully-receipted reproduction of the standard YuE2
WildSongBench protocol on AMD Radeon (W7900D, gfx1100; ROCm) using BOTH your
native PyTorch implementation (`torch-eager`, frozen protocol, official
seeds) and the SGLang serving path. Headline results on the official frozen
evaluator (with disclosed ROCm ASR patches):

| Metric (selected-192) | Official | Arm A native (fresh, W7900D) | Arm B SGLang (fresh) |
|---|---:|---:|---:|
| SongBench GA | 6.7316 | 6.7044 | 6.7376 † |
| MuLan | 0.5068 | 0.4970 | 0.5093 † |
| AllMusicCaps | 0.4054 | 0.4010 | 0.4056 † |
| PER | 8.44 % | **16.83 %** | **17.77 %** † |

† pre-swap-image run (2026-11-14); the this-image Arm B campaign is
regenerating now with identical protocol; per-candidate receipts preserved.

SongBench/MuLan/AMC reproduce the official reference within ±0.03 / ±0.01 /
±0.01. PER does not — and crucially, **your own implementation shows the same
gap on our hardware** (Arm A 16.83 % ≈ SGLang 17.77 % ≈ an independent
October gfx1151 run 17.22 %; uncapped-only selected PER is 16.15 % vs
16.14 % across arms/GPU families; all four ASR passes byte-identical on
384/384 candidates; our independent selection-rule recomputation reproduces
the official aggregation exactly).

**Requests (each maps to a prepared kit):**

1. **Same-audio cross-evaluator (closes the PER question):** may we transfer,
   privately, 384 Arm A + 384 Arm B audio files (2× ~2 GiB; SHA256-manifested;
   performances of licensed WSB lyrics — private channel only, never public)
   for scoring with your CUDA evaluator? Alternatively, please score with
   your environment and return `summary.json` + `per_song.jsonl`.
   `reports/joint_blog_rc/03_CUDA_REFERENCE_HANDOFF.md` has the exact
   procedure; pre-registered interpretations included (≈8–11 % → our ROCm ASR
   backend is the cause; ≈16–18 % → generation-side; we commit to either
   conclusion).
2. **Reference per-song receipts (C2):** official per-song PER receipts for
   the 8.44 % run — means alone cannot localize disagreement.
3. **Evaluator identity:** the exact WildSongBench/evaluator commit (and
   ASR serving configuration) behind the September-12-2026 comparison table,
   so we can exclude evaluator-version drift.
4. **Tolerance confirmation:** our provisional acceptance target is
   |ROCm PER − official| ≤ 2 pp (pre-registered before measurement). Do you
   consider this the right parity criterion for a joint blog?
5. **Protocol confirmations:** (a) four ASR passes with min selection;
   (b) lower-PER candidate selection for all metrics; (c) capped outputs
   retained — all implemented; please flag any deviation.
6. **Blog claims review:** we will send the draft technical article and
   claims matrix (every number → evidence path) for your review before any
   publication. Nothing will imply your endorsement until you say so.
7. **Optional:** Q3O reference execution context (judge identity/config) —
   our 48 GB W7900D may not meet the official judge's memory requirement;
   we will keep Q3O NOT_TESTED rather than substitute a judge.

Everything on our side is reproducible: pinned model/VAE/dataset SHAs,
frozen protocol lock, per-candidate identity chains, and all scripts in the
public repository `AIwork4me/YuE2-SGLang-ROCm` (evidence redacted per
licensing; raw receipts available privately on request).

With respect and appreciation for the excellent benchmark design,
— AIwork4me / joint-blog-RC mission
