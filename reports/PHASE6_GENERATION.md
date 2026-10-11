# PHASE 6 — Full 384-Candidate WSB Generation (living report)

**Status: IN PROGRESS — generation running continuously on gfx1151.**
**Progress is measured from immutable artifacts (result.json + official
verify_result per candidate), never from driver status lines alone.**

## 1. Run configuration (frozen for this run)

- Driver `scripts/run_wsb.py --runs runs/wsb_full`: single pass over the
  frozen manifest, official budgets (cot=full, ode 32, 9000/4096, 1024f+16h),
  original rows/seeds, per-candidate WAV names, atomic finalize, resume on
  verified bundles, rmtree only non-complete dirs.
- Server: `scripts/serve_yue2_rocm.sh` (Phase 3 flag matrix).
- Identity: sglang `ced0ef7d` + patches 0001–0005; models pinned per
  `evidence/model_manifest.json`.
- Milestone watcher auto-commits checkpoints at 10/50/100/192/300/384.

## 2. Artifact-based progress (updated per checkpoint)

| Checkpoint | verified | pending | truncated | failed(open) | notes |
|---|---|---|---|---|---|
| 10/384 (auto) | 10 | 374 | 1 | 0 | `evidence/checkpoint_10.json` |
| 2026-10-12 07:04 audit | 36 | 348 | 1 | 0 | post-INCIDENT-1 recovery; 3 recovered-finalize classified |

Audit command (strict full mode):
`python scripts/verify_wsb_artifacts.py --runs runs/wsb_full` → PARTIAL until
384/384 with zero open problems; classification distinguishes
generated / finalized / verified / pending / driver-status (recovered or open).

## 3. Incident log (full disclosure)

**INCIDENT-1 (2026-10-12 ~05:47–06:30) — self-inflicted, recovered, zero data
loss.** While making `finalize_candidate.py` path-configurable (hardening
task 2), an `import os` was omitted; the running driver spawns the finalizer
as a fresh subprocess per candidate, so three candidates
(`wsb_016_r1_s831035`, `wsb_017_r0_s831018`, `wsb_017_r1_s831036`) recorded
`finalize_failed` although their generation artifacts were fully written.
Recovery: fix applied, candidates re-finalized from their intact on-disk
bundles (no regeneration — byte-identical artifacts, new result.json),
manifest carries appended `complete(recovered-finalize)` records, and the
auditor classifies them `driver:finalize_failed (recovered)` while holding
the immutable bundles authoritative. Generation never stopped. Root cause and
fix recorded here and in git history; regression covered by
`test_recovered_driver_failure_is_not_an_open_defect`.

## 4. Reliability engineering (as implemented)

Atomic finalization (tmp+rename inside write_json), per-candidate official
verification, idempotent resume over verified bundles, retry with backoff on
transport errors, per-run memory sampling (peak GTT recorded in
generation_summary.json), disk checks per checkpoint, stale-dir rmtree before
regeneration (never mixing partial states), artifact hashing in every
result.json, run-identity recomputation in the auditor, driver bookkeeping
never stronger than artifacts.

## 5. Completion criteria (gate to Phase 7)

`verify_wsb_artifacts.py --mode full` returns verdict **FULL**: 384/384
verified, 192 prompts × 2 candidates, zero open problems. Only then does
`run_official_eval.sh` (which enforces the same gate) execute the official
scoring. If the run ends PARTIAL for any reason, the generation verdict is
recorded as PARTIAL and disclosed — never promoted.
