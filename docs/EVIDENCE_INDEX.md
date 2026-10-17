# Evidence Index — where every published number comes from

All times UTC. "Pinned" links reference exact commits so evidence stays reproducible
even if branches move. Verification snapshot: 2026-10-17.

| # | Claim / artifact | Value(s) | Repository ref · commit | Path |
|---|---|---|---|---|
| 1 | gfx1151 strict generation audit | 384/384 verified, verdict `FULL`, 13 truncated-but-valid | `main` · `038acf2b` | [evidence/final_generation_audit.json](../evidence/final_generation_audit.json) |
| 2 | gfx1151 generation wall/summary | 273,385 s wall, finished 2026-10-15T03:00:15 (as recorded) | `main` · `038acf2b` | [evidence/generation_summary.json](../evidence/generation_summary.json) |
| 3 | gfx1151 official scores (PER+SongBench) | unselected-384 GA 6.7177; selected-192 GA 6.68315, PER micro 0.17215 | `main` · `038acf2b` | [evidence/official_scores.json](../evidence/official_scores.json) |
| 4 | gfx1151 official scores (MuLan+AllMusicCaps) | selected-192 MuLan 0.50518, AMC 0.41219 | `main` · `038acf2b` | [evidence/official_scores_additional.json](../evidence/official_scores_additional.json) |
| 5 | gfx1151 platform identity | Radeon 8060S iGPU (gfx1151), Ryzen AI MAX+ PRO 395, host ROCm 7.2.1, torch 2.12.0+rocm7.14.1 wheels | `main` · `038acf2b` | [evidence/environment.json](../evidence/environment.json) |
| 6 | gfx1151 model/dataset pins | YuE2-3B@`1a96eca6`, VAE-legacy@`b54118f0`, WSB@`e361b85a` | `main` · `038acf2b` | [evidence/model_manifest.json](../evidence/model_manifest.json), [evidence/protocol_lock.json](../evidence/protocol_lock.json) |
| 7 | gfx1100 (SGLang) scores snapshot | unselected-384 GA 6.7311, PER 0.22751; selected-192 GA 6.73638, PER 0.17010, MuLan 0.50993, AMC 0.40519 | `main` · `038acf2b` | [evidence/gfx1100/scoring_snapshot.json](../evidence/gfx1100/scoring_snapshot.json) |
| 8 | gfx1100 (SGLang) run handoff | run `wsbfull20261012T0041Z`, v2 scoring pipeline, reviewer verdicts | `main` · `038acf2b` | [reports/upstream/YUE2_FINAL_MERGE_AND_WSB_HANDOFF.md](../reports/upstream/YUE2_FINAL_MERGE_AND_WSB_HANDOFF.md) |
| 9 | gfx1100 (SGLang-Omni) run config | run `omniwsb20261014T1323Z`, sgl-omni `c4841f0c` (=PR#1 head `50c91c08` + comment-only + bench-only export) | `validation/gfx1100-rocm7141` · `137ce40d` | [run_config.json](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/evidence/omni_wsb/full/run_config.json) |
| 10 | gfx1100 (Omni) strict audit | 384/384 verified, 0 missing, verdict `FULL` | `validation/gfx1100-rocm7141` · `137ce40d` | [aggregate_audit.json](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/evidence/omni_wsb/full/aggregate_audit.json) |
| 11 | gfx1100 (Omni) scores | unselected-384 GA 6.73013; selected-192 GA 6.73228, PER 0.17608 | `validation/gfx1100-rocm7141` · `137ce40d` | [scores_summary.json](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/evidence/omni_wsb/scores_summary.json) |
| 12 | Author-acceptance report (three arms + caveats) | arm A/B agreement ±0.002 SongBench; ASR capping disclosed; Q3O NOT RUN | `validation/gfx1100-rocm7141` · `137ce40d` | [OMNI_WILDSOGNBENCH_GFX1100.md](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/author_acceptance/OMNI_WILDSOGNBENCH_GFX1100.md) |
| 13 | Serving BS=1 + C=1/2/4/8 | P50 217.3 s; RPS 0.0046 constant; delivered concurrency 1 | `validation/gfx1100-rocm7141` · `137ce40d` | [OMNI_BS1_CONCURRENCY_GFX1100.md](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/author_acceptance/OMNI_BS1_CONCURRENCY_GFX1100.md) |
| 14 | Corrected serving metrics (RTF erratum) | speed multiplier 1.030×; client RTF 0.975 | `validation/gfx1100-rocm7141` · `137ce40d` | [SERVING_PERFORMANCE_CORRECTION.md](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/final_acceptance/SERVING_PERFORMANCE_CORRECTION.md), [CORRECTED_METRICS.json](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/evidence/omni_wsb/serving/CORRECTED_METRICS.json) |
| 15 | Evidence integrity closure | pilot/full artifact mix-up fixed; sha256 anchors matched | `validation/gfx1100-rocm7141` · `137ce40d` | [EVIDENCE_INTEGRITY_CLOSURE.md](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/final_acceptance/EVIDENCE_INTEGRITY_CLOSURE.md) |
| 16 | Final merge handoff | last YuE2 lint blocker closed (`b91b9544`); NOT-YET-VERIFIED ledger (H800, upstream CI, merges) | `handoff/yue2-upstream-merge-readiness` · `40bd59f9` | [10_FINAL_MERGE_HANDOFF.md](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/40bd59f94079345917b526a3e2ee49c8a9f1f867/reports/final_merge_closure/10_FINAL_MERGE_HANDOFF.md) |
| 17 | Upstream PR states | all five PRs OPEN/unmerged (live check 2026-10-17) | GitHub API | see README §5 links |
| 18 | Prepared style commits | `ae11c6ad`, `b91b9544` (AIwork4me/sglang-omni); `1a9f2d92` (AMD-sglang-benchmark-fork) | GitHub API | see README §5 links |

## Arm and metric conventions

- **Unselected arm** = all 384 generated candidates. **Selected arm** = official
  PER-based best-of-2 per prompt (192 candidates), reused for MuLan/AllMusicCaps.
  The two arms are never mixed in a single figure.
- PER = phoneme error rate (lower is better); SongBench Global Avg = mean of the
  seven SongBench dimensions (0–10); MuLan/AllMusicCaps = audio-text similarity
  (higher is better).
- gfx1151 numbers come only from the gfx1151 run (`runs/wsb_full`); gfx1100 numbers
  only from the two W7900 runs (`wsbfull20261012T0041Z`, `omniwsb20261014T1323Z`).
  No value is copied across platforms.

## Reviewer verdicts

Per-phase independent reviews live in [`../reviews`](../reviews); consolidated
verdicts: [FINAL_INDEPENDENT_REVIEWS.md (validation branch)](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/final_acceptance/FINAL_INDEPENDENT_REVIEWS.md),
[merge-readiness reviews](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/40bd59f94079345917b526a3e2ee49c8a9f1f867/reports/merge_readiness/FINAL_INDEPENDENT_REVIEWS.md),
and the 2026-10-17 documentation-audit reviews linked from the documentation PR.
