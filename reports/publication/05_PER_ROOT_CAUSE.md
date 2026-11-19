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

## 2. Observed tail, NOT causal attribution

| Observation | Scope | Interpretation |
|---|---|---|
| 112 capped ASR outputs, capped-only PER 35.3% | Unselected 384 | Correlated with higher error; causation not established |
| Uncapped PER 19.14% | Unselected 384 | CANNOT directly compare with official selected-192 8.44% |
| 10 empty transcripts; 11 PER=1.0 | Unselected 384 | Overlapping groups; do NOT sum contributions |
| 56 selected capped outputs | Selected 192 | Selected-group edit totals still needed |
| 24 selected songs PER>30% | Selected 192 | Weak candidates exist, source unproven |

The official-to-ROCm difference is +9.33 percentage points for selected-192.
No defensible percentage-point contribution can be assigned to capping,
empty transcripts or sampling until matched selected-192 denominators and
overlapping group membership are computed. A same-audio reference-vLLM
versus ROCm-Transformers ASR A/B is also required.

## 3. What the residual is NOT (pilot-controlled evidence)

- **Cannot yet exclude evaluator inflation:** the substituted evaluator
  scored an Arm A candidate at **6.47%** and a historical W7900 SGLang
  prompt-0 candidate at **5.99%**. This establishes that low PER values
  are POSSIBLE, not equivalence with the reference vLLM ASR evaluator.
  Same-audio cross-evaluator controls are still required.
- **Not language skew:** zh/en are balanced (17.7/17.8).
- **Repeat consistency is not cross-backend equivalence:** the four ASR
  passes were internally consistent. Comparison with the official vLLM
  backend and the 328-receipt concurrent run is not yet complete.

## 4. Leading hypotheses (NOT causally closed)

Generation-distribution differences at song level are a leading hypothesis,
not an established explanation of the official-to-ROCm delta. Some
generations have mis-sung/garbled vocals (e.g. the Arm A r1 pilot scored
19.4% PER), but the measurement also changes ASR implementation.
Capped-only 384-candidate averages and selected-192 official aggregates
must not be directly subtracted as equivalent populations.
A selected-192 phoneme-weighted tail decomposition is still required.
These factors may overlap; estimated components must not be summed. Whether the official H800
campaign produced proportionally fewer such weak songs (hardware/backend
sampling differences at the margin) cannot be decided without either:
(a) official per-song PER receipts (not published; **author request prepared**), or
(b) scoring official audio with our evaluator (audio not distributed), or
(c) running the official vLLM evaluator backend on our audio (needs CUDA host).

**Status: OPEN — the tail distribution is characterized, but root cause is
not established.** An official vLLM-vs-transformers same-audio comparison,
a selected-192 decomposition with correct denominators, and ideally official
per-song scores are needed before assigning the gap to generator or evaluator.
SongBench is independently close to the official mean (Δ+0.006);
no statistical equivalence claim is made on the basis of mean alone.

## 5. Claims permitted / not permitted

- PERMITTED: "PER with the disclosed ROCm evaluator: 17.77% [bootstrap
  CI 15.2–20.7] versus official 8.44%. Capped ASR and weak selected
  candidates are observed, but cross-evaluator equivalence and causal
  attribution remain unresolved."
- NOT PERMITTED: "ROCm PER equals official" / "the gap is caused by AMD
  hardware" / "the official number is wrong".

## 6. Artifacts

- `evidence/publication/armB_campaign/campaign_summary.json` (this analysis)
- `/data/yue2-runs/armB_wsb_full/scores/per_song.jsonl` (384 receipts, solo)
- `/data/yue2-runs/armB_wsb_full/scores_concurrent_partial/` (328-receipt
  concurrent run, preserved for the determinism diff)
- `evidence/publication/per_rca/armA_pilot_per.json` (evaluator-control pilot)
