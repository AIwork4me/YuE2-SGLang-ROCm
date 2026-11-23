# RC4.1 M4 — Evidence discrepancies found and reconciliation

Audit tool: `scripts/verify_rc4_evidence_consistency.py` (new; re-runs in
CI via `tests/test_evidence_consistency_rc41.py`). Declared method:
linear-interpolation percentiles, wall rounded 1 dp, multiplier 4 dp.

## Discrepancies found (all fixed in this mission)

| # | Item | Was | Now | Class |
|---|---|---|---|---|
| 1 | raw CSV row count cited by 03_PERFORMANCE_SUMMARY.md / FINAL_REPORT_ZH.md | 786 | **791** (recounted from the CSV: 768 campaign_frozen + 23 rc4_fresh) | stale mid-run claim |
| 2 | Arm A fresh n | "2 (+6 in flight)" | **7** (final CSV rows) | stale mid-run claim |
| 3 | 03_aggregates.json p95 values | mixed methods (armA groups 'higher' interp, armB warm 'lower' — computed at different times on growing data) | recomputed uniformly (declared linear): armA camp 1033.1→1028.2, armA fresh 858.6→809.5, armB camp 429.6→429.2, armB cold 422.4→410.7, armB warm 318.9→335.6; multiplier p95s likewise | stale aggregate drift |
| 4 | "51.5 GiB" in FINAL_REPORT_ZH.md / 03_RESOURCE_ENVELOPE.md | 51.5 GiB | **51.5 decimal GB (= 47.98 GiB)**; 51522830336 bytes stated | unit mislabel |
| 5 | 01_REPRODUCIBILITY_VERDICT.json pilot_scoring | mid-run placeholder (gpu-window pending) | PASS with all four metrics complete=true (final state was already evidenced in 05_CI_AND_GPU_REGRESSION.md) | stale verdict |
| 6 | referenced-but-untracked CSVs (02_RELIABILITY_MATRIX.csv, 02_MEMORY_LIFECYCLE.csv, 03_CONCURRENCY_RESULTS.csv) | present only under /data/yue2-runs/rc4_evidence/ (case A: existed locally, never committed) | committed to reports/w7900_rc4/ after public-evidence-guard + lyrics-detector scans passed (numeric/HTTP data only) | missing public evidence |

Classification of the missing-CSV cases (mission M4.4 taxonomy):
A (exists locally, not committed) for all three; no ignored-path issue
(`.gitignore` patterns untouched); no protected content (guards PASS).

## Non-discrepancies verified

- per-group n: 384/384/7/2/14 match the CSV exactly
- p50/mean/min/max wall: match under the declared method for all groups
- duplicate candidates: none (run_id+prompt_id+seed unique across 791)
- mixed-source aggregation: none (aggregates keyed by arm|source|window;
  no cross-source P50/P95)
- README public metrics: no 786/51.5GiB/PENDING artifacts introduced;
  README RC4-era tables re-checked (see 04_README_REVIEW.md)

## Frozen evidence protection

SHA256 manifests of /data/yue2-runs/{armA_wsb_full, armB_wsb_full,
rc4_evidence} taken before any RC4.1 GPU work (15,825 files) and re-hashed
after: **byte-identical** (00_FROZEN_EVIDENCE_INTEGRITY.md). No frozen
audit.json, score receipt, audio or log was modified. All RC4.1
experiments used new directories/run_ids under
/data/yue2-runs/rc4_1_evidence/ and rc4_1_native_pilot/.

## Regression protection (CI)

`tests/test_evidence_consistency_rc41.py` (12 tests) fails on: count
mismatch, duplicate rows, stale aggregate value, stale 786 claim, GB/GiB
mislabel, stale PENDING, missing required CSV, non-complete status row,
regenerate-only-touches-aggregates; plus a live in-repo consistency test
that must PASS on every future commit.
