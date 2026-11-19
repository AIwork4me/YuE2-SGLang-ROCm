# 03 — PER Root-Cause: cross-arm causal analysis (M3, joint-blog-RC edition)

**Date:** 2026-11-19 · **Author environment:** W7900D (gfx1100, 48 GB), ROCm 7.2.1
host userspace, evaluator venv torch 2.10.0+rocm7.14.1 wheels, pinned WSB tree
(manifest sha256 `859e5225…`).

## 1. The measurement problem (unchanged)

Official standard YuE2 reference (WSB README, Sept-12-2026 comparison):
**PER 8.44 %** (selected-192). Prior best ROCm measurement: 17.77 %
(fresh Arm B, pre-swap image, 2026-11-14, disclosed evaluator patches).
Gap ≈ **+9.3 pp**, i.e. roughly 2×.

## 2. NEW controlled evidence: the official implementation itself, on ROCm

The fresh Arm A campaign (this image; **native PyTorch `torch-eager` — the
authors' own implementation**, frozen protocol, pinned weights, official
seeds) completed 384/384, audit FULL, and was scored with the same frozen
disclosed evaluator:

| Arm | Implementation | GPU | Selected-192 PER micro | 95 % CI (prompt bootstrap) | Receipts |
|---|---|---|---:|---|---|
| **Arm A fresh** | official torch-eager | W7900D (gfx1100) | **16.83 %** | [14.87, 18.92] | `/data/yue2-runs/armA_wsb_full/scores/per_song.jsonl` (384 rows) |
| gfx1151 (Oct) | SGLang | Radeon 8060S (gfx1151) | **17.22 %** | [14.93, 19.80] | `evidence/per_song.jsonl` (384 rows) |
| Arm B fresh (pre-swap) | SGLang | W7900 (pre-swap img) | 17.77 % | [15.20, 20.68] | summaries only (per-song rows on prior image) |
| Arm B fresh (this image) | SGLang | W7900D | *in progress* | — | regenerating now |

Selection rule recomputed independently (min per → edits → |hyp−ref| →
repeat index) and **reproduces the evaluator's own summary exactly**
(0.168292…), validating the analysis path.

## 3. Decomposition with exact denominators (selected-192)

| Group | Arm A (n) | Arm A PER | gfx1151 (n) | gfx1151 PER |
|---|---:|---:|---:|---:|
| all selected | 192 | 16.83 % | 192 | 17.22 % |
| ASR-capped (truncated) | 36 | 19.28 % | 44 | 20.76 % |
| **uncapped** | 156 | **16.15 %** | 148 | **16.14 %** |
| PER == 1.0 | 3 | 6.8 % of selected edits | 3 | 5.7 % of edits |
| empty transcripts | 3 | (subset of PER=1) | 3 | (subset) |
| PER > 30 % | 23 | — | 23 | — |
| unselected capped (of 384) | 72 | — | 88 | — |

Overlapping memberships are reported explicitly; contributions are **not
summed**. Groups `capped ∧ PER=1` overlap: Arm A 3/3 PER==1 are all
capped-ASR candidates.

**Finding 1 — capping is not the gap.** Even excluding every capped
candidate, both arms sit at ≈ 16.1 %, i.e. +7.7 pp above the official 8.44 %.

**Finding 2 — the gap is common-mode, not arm-specific.** Uncapped selected
PER agrees to 0.01 pp across: official-implementation-on-discrete-W7900D vs
SGLang-on-iGPU-gfx1151 vs SGLang-on-W7900. Whatever inflates PER is shared by
all three stacks and both GPU families.

## 4. Paired per-prompt analysis (Arm A × gfx1151, n = 192 prompts)

Unit = prompt; unselected both-candidate micro PER per prompt; identical
frozen prompts and official seeds on both sides.

| Statistic | Value |
|---|---|
| Spearman ρ | **0.755** |
| Pearson r | 0.349 |
| mean paired difference (gfx1151 − Arm A) | +1.11 pp |
| 95 % CI of paired difference | [−3.73, +5.59] pp |

**Finding 3 — prompt-structural difficulty is shared.** Rank correlation is
high: the same prompts are hard everywhere. The paired arm difference is not
significant. The +8…9 pp offset versus the official baseline is a systematic
common-mode shift, not sampling noise and not backend-specific.

## 5. ASR determinism

All 4 ASR passes produce byte-identical transcripts for **384/384**
candidates in BOTH arms (greedy decoding; `asr_repeats` identical).
**Finding 4 — transcript noise is not a factor**; any evaluator-side effect
is deterministic bias, not variance.

## 6. Audio-quality cross-check

Official judges that do NOT depend on the ASR/phonemization layer all
reproduce the official reference within tolerance on the same fresh audio
(Arm A): SongBench 6.7044 vs 6.7316 (Δ −0.027), MuLan 0.4970 vs 0.5068
(Δ −0.010), AMC 0.4010 vs 0.4054 (Δ −0.004). If generation quality on ROCm
were broadly degraded, these would drift too. This does not *prove* the audio
is lyrically equivalent — but it removes the "everything is worse"explanation
and leaves the ASR/phonemization measurement layer as the prime suspect.

## 7. Hypothesis ledger (updated; evidence-tagged)

| # | Hypothesis | Status after this analysis |
|---|---|---|
| H1 | ROCm ASR backend (Qwen3-ASR via transformers, patch 0007) systematically mis-transcribes vs the official CUDA serving | **PRIME SUSPECT** — common-mode, deterministic, survives uncapped filtering; SongBench/MuLan/AMC parity on the same audio; requires same-audio cross-evaluator (A2/B2/C1) to close |
| H2 | Generation numerics on ROCm (bf16 kernels) degrade lyric fidelity in both stacks | POSSIBLE CO-FACTOR — cannot be excluded without official per-song receipts (C2) or CUDA-side scoring of our audio (A2/B2); note 6.47 %/5.99 % pilot singles show low PER is achievable |
| H3 | Evaluator/phonemization version drift vs the authors' Sept-2026 run | OPEN — pinned tree verified against WSB SHA256SUMS, but the authors' exact evaluator commit for 8.44 % is unconfirmed; included in author request |
| H4 | Aggregation/selection difference | **EXCLUDED** — our independent selection-rule recomputation reproduces the official semantics (4-pass min, lower-PER candidate) and the evaluator's own aggregates exactly |
| H5 | ASR capping / truncation policy | **EXCLUDED as primary cause** — uncapped-only PER ≈ 16.1 % on both arms |
| H6 | Language skew | **EXCLUDED** — zh/en balanced (Arm A: 16.4 %/17.2 % selected; pre-swap B: 17.7/17.8) |
| H7 | Serving-stack-specific (SGLang) | **WEAKENED SHARPLY** — official torch-eager arm shows the same gap |

## 8. What closes this (M3.2 matrix status)

| Cell | Audio | Evaluator | Status |
|---|---|---|---|
| A1 | Arm A fresh | ROCm | **DONE** 16.83 % [14.87–18.92] |
| B1 | Arm B pre-swap | ROCm | **DONE** 17.77 % [15.20–20.68] |
| B1′ | Arm B this-image | ROCm | in progress (campaign running) |
| A2/B2 | same Arm A/B audio | official CUDA | **BLOCKED_EXTERNAL** — kit prepared (`03_CUDA_REFERENCE_HANDOFF.md`) |
| C1 | author reference audio | ROCm | **BLOCKED_EXTERNAL** — request prepared |
| C2 | author reference audio | official CUDA | **BLOCKED_EXTERNAL** (authors' own 8.44 % context) |

**M3 verdict: OPEN (not scientifically closed).** Internal evidence
converges on H1 with H2 as co-factor, but per mission rules no causal
claim is made until a same-audio cross-evaluator comparison executes.
Acceptance target: |ROCm PER − official PER| ≤ 2 pp (provisional,
pre-registered, author confirmation requested).

## 9. Reproducibility

- Script: `scripts/per_cross_arm_analysis.py` (deterministic, seeds fixed;
  prompt-level bootstrap n=10 000).
- Inputs pinned by content: Arm A receipts under
  `/data/yue2-runs/armA_wsb_full/scores/` (audio SHA256 per candidate in
  rows); gfx1151 receipts in-repo (`evidence/per_song.jsonl`).
- Aggregates only in this report; raw text-bearing receipts never published.
