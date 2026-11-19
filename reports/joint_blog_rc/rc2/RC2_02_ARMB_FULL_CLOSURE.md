# RC2_02 — Arm B full closure (INTERIM TRACKER — campaign running)

**Do not upgrade anything here before receipts exist.** This file exists so
any successor session can resume closure mechanically.

## Live campaign identity (verified at RC2 session start, 2026-11-19T02:49Z)

| Item | Value |
|---|---|
| Run ID | `armB_full_20261119T015756Z` |
| Started | 2026-11-19T01:57:56Z (gpu.lock acquired by launcher gateway) |
| Source tree | live checkout `fee027d` (PR #14 head; driver byte-identical at PR #15 — RC2_00 §4) |
| Model / VAE | `m-a-p/YuE2-3B@1a96eca6` / `m-a-p/YuE2-Vae-legacy@b54118f0` (sha-pinned in run_config) |
| Dataset | `m-a-p/WildSongBench@e361b85a`, manifest sha `859e5225…` |
| SGLang commit / patchset | `ced0ef7d` / `c1e04454…` |
| Protocol | frozen lock 2026-11-11; seeds 831001+i / 831019+i; cot=full; ode 32; 9000/4096; VAE 1024+16 |
| Supervisor | mission_chain PID 3363794, stage cadence 600 s |

## Progress log (append-only; recompute from journal, never hardcode)

- 02:49Z: 10/384 complete (0 retries)
- 03:27Z: 18/384 · 03:37Z: 20 · 03:47Z: 26 · 04:07Z: 30 (approx, journal cadence)
- 04:47Z: 34/384 · 04:57Z: 36/384 — all `complete`, `retries=0`, wall 200–286 s/cand
- ETA generation ≈ 2026-11-20T23:00Z (±3 h) → chain proceeds automatically:
  `armB_audit` → `armB_score_per_sb` → `armB_score_mulan_amc` → `done`

## Closure checklist (execute when terminal)

1. [ ] journal recompute = 384 unique complete ids (prefix counting per PR #16)
2. [ ] `verify_wsb_artifacts.py --mode full` → audit.json verdict FULL
3. [ ] `verify_provenance.py --runs armB_wsb_full` → 0 violations (C2.1 chain)
4. [ ] both scoring stages: rc=0 + summary.complete=true + per_song.jsonl 384 rows
5. [ ] record the EXACT tree SHA active at scoring time (lineage!)
6. [ ] generate `armB_bundle_manifest.json` (builder in
       `/data/yue2/tmp/rc2_kit_validation/build_bundle_manifest.py`)
7. [ ] four-metric comparison vs fresh Arm A + official baseline; paired
       prompt-level stats (reuse `per_cross_arm_analysis.py`)
8. [ ] emit `RC2_02_FRESH_ARMA_ARMB_COMPARISON.csv` +
       `RC2_02_BENCHMARK_MANIFEST.json`; flip G3 in the gate ledger

## Contingencies

- Driver dies → supervisor relaunches resume-safe (run_id reuse; launcher
  flock no-op); RC2 fix (PR #16) additionally guarantees resumed candidates
  count toward the gate **once deployed to the live tree** — deployment is
  owner-gated; without it, verify counts by prefix manually if a torn tail
  ever occurs (see RC2_01 P1-1 for the failure mode).
- Audit NOT FULL → chain blocks with `blocked_reason`; inspect, never edit
  frozen result files.
