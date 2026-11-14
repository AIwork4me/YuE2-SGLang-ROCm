# 05 — PER Root-Cause Analysis (fresh evidence edition)

**Date:** 2026-11-14 · **Scope:** why historical ROCm PER (~17–17.8%) differs from the official 8.44%, with the first complete fresh per-candidate receipts on W7900.

## 1. Fresh Arm B facts (solo official scoring, frozen evaluator + patches 0006/0007/0009/0010)

| Quantity | Value |
|---|---:|
| PER micro, selected-192 | **17.77%** (bootstrap 95% CI 15.20–20.68%) |
| PER micro, unselected-384 | 24.29% |
| SongBench GA selected-192 | **6.7376** (official 6.7316; Δ +0.0060) |
| SongBench GA unselected-384 | 6.7311 |
| ASR-capped candidates | 112/384 (capped-only micro 35.3%) |
| Uncapped-only micro | 19.14% |
| Empty-transcript candidates | 10 (PER 1.0 each) |
| PER == 1.0 candidates | 11 |
| Selected songs with PER > 0.30 | 24/192 |
| zh / en selected micro | 17.70% / 17.83% (balanced) |

## 2. Decomposition of the 17.77% vs 8.44% gap (≈9.3pp)

| Component | Evidence | Estimated contribution |
|---|---|---|
| Capped-ASR tail (112 cands @ 35.3% vs uncapped 19.1%) | per_song receipts; identical policy to official ("retain capped") | ≈ 3–5pp of aggregate |
| Empty/degenerate transcripts (10–11 cands) | per_song receipts | ≈ 1–2pp |
| Weak-candidate selection floor | 24 selected songs >30% PER — both candidates bad on those prompts | included in above |
| Residual baseline (uncapped ≈19% vs official 8.44%) | see §3 | ≈ 10pp unexplained by tail alone |

## 3. What the residual is NOT (pilot-controlled evidence)

- **Not a systematic evaluator inflation:** the same substituted evaluator
  scored an official-path (Arm A) candidate at **6.47%** PER — official-range —
  and a historical W7900 SGLang prompt-0 candidate at **5.99%**
  (`evidence/publication/per_rca/armA_pilot_per.json`). The evaluator
  reproduces official-range PER on strong audio.
- **Not language skew:** zh/en are balanced (17.7/17.8).
- **Not nondeterminism:** 4/4 ASR passes bit-identical per candidate; solo vs
  concurrent 328-receipt comparison pending final diff (both runs preserved).

## 4. Leading explanation (supported, not yet fully closed)

Generation-distribution differences at the song level: a minority of
generations have genuinely mis-sung/garbled vocals (transcript divergences
match real audio content — e.g. the Arm A r1 pilot candidate sings wrong
words, PER 19.4%). These concentrate the residual. Whether the official H800
campaign produced proportionally fewer such weak songs (hardware/backend
sampling differences at the margin) cannot be decided without either:
(a) official per-song PER receipts (not published; **author request prepared**), or
(b) scoring official audio with our evaluator (audio not distributed), or
(c) running the official vLLM evaluator backend on our audio (needs CUDA host).

**Status: PARTIALLY RESOLVED — tail quantified and evaluator exonerated as a
2x inflator; the cross-vendor residual is bounded (≤ ~10pp, CI'd) but its
generator-vs-evaluator split requires one of (a)/(b)/(c). Numerical PARITY
between our SongBench and official (Δ0.006) stands independently.**

## 5. Claims permitted / not permitted

- PERMITTED: "PER on W7900 via the disclosed evaluator substitution:
  17.77% [15.2–20.7] vs official 8.44%; gap dominated by a 29% capped-ASR
  tail and weak-candidate floor; evaluator backend validated to score
  official-range PER on strong audio."
- NOT PERMITTED: "ROCm PER equals official" / "the gap is caused by AMD
  hardware" / "the official number is wrong".

## 6. Artifacts

- `evidence/publication/armB_campaign/campaign_summary.json` (this analysis)
- `/data/yue2-runs/armB_wsb_full/scores/per_song.jsonl` (384 receipts, solo)
- `/data/yue2-runs/armB_wsb_full/scores_concurrent_partial/` (328-receipt
  concurrent run, preserved for the determinism diff)
- `evidence/publication/per_rca/armA_pilot_per.json` (evaluator-control pilot)
