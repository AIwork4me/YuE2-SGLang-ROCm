# Evidence Index — where every published number comes from

All times UTC. "Pinned" links reference exact commits so evidence stays reproducible
even if branches move. Verification snapshot: 2026-10-17 (historical) · RC3/RC4
additions 2026-11-22 · **RC5.1/RC6 additions 2026-11-27 (current generation —
read the RC6 developer reference first:
[reports/developer_reference/](../reports/developer_reference/))**.

## RC5.1 / RC6 current generation (read this first)

| run_id / report | what it proves | entry point |
|---|---|---|
| `rc5_armB_latest_upstream_20261124T065451Z` | 384/384 generation on upstream `c67d541a` + import guards; 380/384 byte-identical vs the historical stack | [reports/w7900_rc5/rc5_1/](../reports/w7900_rc5/rc5_1/) |
| RC5.1 five-metric scoreboard | SongBench 6.736891 · PER 17.7699% (frozen) / 8.4488% (corrected arm) · MuLan 0.509395 · AMC 0.405181 · Q3O 4.393986 (ROCm-adapted) | `06_FIVE_METRIC_SCOREBOARD.csv` |
| RC6 developer reference | scientific closure (determinism, evaluator identity, 2×2 PER attribution, Q3O boundary), developer golden path, fresh-clone reproduction, author/AMD packages, release gates | [reports/developer_reference/README.md](../reports/developer_reference/README.md) |

## Current-generation runs (W7900D, RC2–RC4 lineage — historical reference)

| run_id | backend | GPU | finished (UTC) | source | pins | audio | audit | metrics (selected-192) | limitations | evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| `armA_full_20261116*` (dir `armA_wsb_full`) | native torch-eager 2.10.0+rocm7.1 | W7900D gfx1100 | 2026-11-18 | RC2 campaign (`reports/joint_blog_rc`) | model `1a96eca6` · VAE `b54118f0` · WSB `e361b85a` · patchset `c1e0445…` | 384 | FULL 384/384 (audit.json predates truncation-schema fix; corrected count = 5 truncated, see RC4 04_TRUNCATION_AUDIT) | SongBench/MuLan/AMC in `scores/summary.json`; PER with ROCm ASR backend | PER parity vs CUDA OPEN (G4) | `/data/yue2-runs/armA_wsb_full` (receipts hashed in RC4 M0) |
| `armB_full_20261119T015756Z` (dir `armB_wsb_full`) | SGLang ced0ef7d + patches 0001-0005/0008, torch 2.12.0+rocm7.14.1 | W7900D gfx1100 | 2026-11-20 09:34 | RC3 campaign | same pins | 384 (0 failures/retries) | FULL 384/384, identity reverified 384/384 | SongBench **6.7383** · MuLan **0.5092** · AMC **0.4056** · PER **17.76%** (official ref 8.44%) | PER parity OPEN; LEGACY provenance honestly marked | `/data/yue2-runs/armB_wsb_full`; RC3 report `reports/w7900_rc3/01_ARMB_*` |
| `rc4_pilot_armA` / `rc4_pilot_armB` | same stacks, FRESH clone + fresh venvs | W7900D | 2026-11-22 16:05 / 16:38 | RC4 fresh-clone reproduction | same pins (re-verified) | 2+2 | PILOT 0 problems each | (pilot-scale; not comparable to 192-prompt metrics) | pilot n=1 prompt | `reports/w7900_rc4/01_*` |
| RC4 perf window (`rc4_perf_armB` etc.) | same | W7900D | 2026-11-22 | RC4 M3 | same | see raw CSV | n/a (performance only) | wall/RTF distributions | fresh-sample n smaller than campaign n=384 (stated per figure) | `reports/w7900_rc4/03_*` |

Historical runs (pre-RC2, earlier image) follow; **never mix their metrics with the
current-generation table above** (different patchsets/source commits).

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


---

## Publication-readiness mission (2026-11, branch feat/yue2-rocm-publication-readiness)

| Claim | Evidence (path on this branch) |
|---|---|
| Physical W7900 gfx1100 48GiB verified; GPU compute smoke | reports/publication/00_ENVIRONMENT.json |
| Baseline repo + upstream state audit (all PRs still open, weights unchanged) | reports/publication/00_BASELINE_AUDIT.md, 01_UPSTREAM_GAP_ANALYSIS.md |
| Pinned downloads SHA256-verified (model/VAE/dataset/evaluator) | /data/yue2/logs/download_pins.log (ALL PINS VERIFIED) + configs/benchmark.lock.yaml |
| torch 2.10.0+rocm7.1 works on gfx1100; official torch backend broken (mha_varlen seqused_k) → torch-eager is the ROCm path | reports/publication/02_RCA_LEDGER.md RCA-6 |
| Evaluator reconstructed bit-identically (0006: sha 6a4a53ed) + 0007/0009 applied + 0010 disclosed | reports/publication/02_RCA_LEDGER.md, release.json disclosure |
| Arm A official-path pilot PER on W7900 (6.47%/19.40%, official-range) | evidence/publication/per_rca/armA_pilot_per.json |
| Evaluator-assets hub-based pinned fetcher (proxy-hardened) | scripts/fetch_eval_assets_hub.py |
| Arm B fresh campaign progress + milestones | evidence/publication/armB_campaign/progress.jsonl |
| Security + licensing audits | reports/publication/09_SECURITY_AUDIT.md, 09_LICENSE_AND_ATTRIBUTION.md |

Live campaign receipts (absolute paths on the bench machine, mirrored at
milestones): /data/yue2/logs/, /data/yue2-runs/.

---

## RC5 — latest upstream on the W7900D (2026-11-24, IN PROGRESS)

Snapshot for review; the mission is not finished. Nothing below is a
selected-192 benchmark result. Status: reports/w7900_rc5/INTERIM_STATUS_ZH.md.

| Claim | Evidence (path on this branch) |
|---|---|
| Physical W7900D gfx1100 47.98 GiB, BDF 0000:03:00.0; identity chain framework → HIP → PCI → render node → KFD → UUID closed; fp32/bf16 matmul + SDPA compute probe | reports/w7900_rc5/00_ENVIRONMENT.json, 01_REAL_GPU_IDENTITY_NEGATIVES.json |
| No authorised off-machine backup (owner: no backup host); same-host second-volume restore drill 12/12 candidates, 132 files hash-exact | reports/w7900_rc5/00_STORAGE_AND_BACKUP_PLAN.md, 00_RECOVERY_DRILL.json |
| RC4.1 GPU-lock race reproduced (5.96 s window, 47 samples) and closed (0 samples) | reports/w7900_rc5/01_LOCK_RACE_REPRO.json |
| P0/P1 findings of the RC4.1 review closed; 6/6 real-GPU readiness controls | reports/w7900_rc5/01_P0_P1_CLOSURE.json, 01_RC42_INDEPENDENT_REVIEW.md, 01_REAL_GPU_READINESS_CONTROLS.json |
| 38 mutations killed; 3 test gaps found and closed | reports/w7900_rc5/01_MUTATION_RESULTS.json, 01_NEGATIVE_CONTROL_MATRIX.csv |
| Upstream PR #42106 head c67d541a frozen; only 2 import-guard patches needed; effective tree + dependency hashes | reports/w7900_rc5/02_UPSTREAM_DELTA_REVIEW.md, 02_PATCH_RECONCILIATION.csv, 02_EFFECTIVE_RUNTIME_MANIFEST.json, 02_CAPABILITY_MATRIX.json |
| 12 pre-registered pilot candidates byte-identical (audio.flac SHA256) to the frozen historical Arm B manifest | reports/w7900_rc5/03_PILOT_SELECTION.json, 03_PILOT_VS_HISTORICAL_MANIFEST.json |
| Pilot (12 UNSELECTED candidates, shard mode): SongBench Global 6.5459; MuLan 0.3756; AllMusicCaps 0.3757; PER micro 0.6654 (ASR batch_size=1 variant) | reports/w7900_rc5/03_PILOT_ACCEPTANCE.json |
| Q3O judge memory budget from safetensors headers (65.68 GiB BF16 total, 54.0 GiB MoE experts); 24-layer draft corrected to 48 x 1.125 GiB; placement measured | reports/w7900_rc5/07_Q3O_MEMORY_BUDGET.json |
| Campaign paused by operator at 20/384 (rc=143 CLEAN); checkpoint 16 verified to the second volume, 4 candidates not yet backed up; ~28 h projected for the rest | reports/w7900_rc5/04_CAMPAIGN_PAUSE_SNAPSHOT.json (scripts/rc5_campaign_snapshot.py) |
| Q3O judged on the 48 GB W7900D for the first time: 1 retained run COMPLETE (q3o 4.83, 176 s/candidate, VRAM 43.1 GiB, host peak 50.1/55 GiB); two earlier single runs not retained (disclosed); receipt wording correction | reports/w7900_rc5/07_Q3O_48GB_PILOT.json |
| Q3O MoE placement blocks equal to the verbatim HF loop (<= 2 bf16 ulp on tie-free inputs); 9 tests x 4 environments; 16 arithmetic mutation controls: 15/16 KILLED on GPU in both torch builds (survivor disclosed as near-equivalent) | reports/w7900_rc5/07_Q3O_MOE_EQUIVALENCE.json, tests/test_rc5_q3o_moe.py, scripts/mutation_controls_q3o_moe.py |
| torch.topk breaks ties nondeterministically on the evaluator build (2.10.0+rocm7.14.1, W7900D): greedy MoE judges built on it are not reproducible run-to-run | reports/w7900_rc5/07_Q3O_MOE_EQUIVALENCE.json (finding_topk_nondeterminism) |

## RC5.1 (2026-11-24..27, this branch, latest-upstream full reproduction)

| run_id | backend | GPU | finished (UTC) | source | audio | metrics | evidence |
|---|---|---|---|---|---|---|---|
| `rc5_armB_latest_upstream_20261124T065451Z` | SGLang c67d541a (author PR #42106) + import-guard patches 0001/0003/0008, torch 2.12.0+rocm7.14.1 | W7900D gfx1100 | 2026-11-26 00:17 | RC5.1 campaign (resumed from 20/384 with journal-disclosed driver revision) | 384/384 (380 byte-identical to Arm B; 4 FLAC-container-only) | SongBench 6.736891 · PER 17.7699% (frozen) / **8.4488% vLLM-corrected arm** · MuLan 0.509395 · AMC 0.405181 · Q3O 4.393986/5 ROCm-adapted 192/192 | [`rc5_1/`](../reports/w7900_rc5/rc5_1/) — FINAL_REPORT_ZH.md, 08_RELEASE_GATE_LEDGER.json |
