# PR #10 — Final independent CPU-only review and security closure

Review date: 2026-11-15. Scope: GitHub repository artifacts and CI only;
**NO access to a W7900 host, active Arm A PID, /data files, or live job status.**

## Ground truth of repository state

- Main branch merged security PR #7 at `ba99c4d` (2026-11-15 06:39:14Z), CI [43686423317](https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/43686423317) success.
- PR #8 remains Draft; its CPU driver improvements overlap PR #10, as detailed in `01_PR_CONFLICT_MATRIX.md`. Do NOT blindly cherry-pick or auto-close.
- PR #9 remains Draft with Arm A's original code HEAD `8c242bae`; this mission does not touch it.
- PR #10 changes are solely on `fix/w7900-cpu-only-risk-closure-20261115`; keep Draft and do NOT hot-deploy new driver while Arm A runs.
- Latest CI and exact PR #10 HEAD should be read from GitHub checks at the time of review; documents never authorize using stale runs.

## Independent findings and actual fixes

### Security: tier coverage must not be overstated

Previous CI emitted `tier1=on tier2=OFF` while passing. The new scanner adds
`--require-ground-truth` for a rights-cleared release audit, which fails if
the frozen Manifest is absent or its checksum does not match. English long
lyric windows are now included (distinctiveness threshold to reduce false
positives); malformed CSV and unreadable tracked files fail closed.
Synthetic end-to-end Tier 2 tests run in public CI without distributing
official data.

**Residual:** Real WildSongBench Tier 2 on the latest implementation is
NOT TESTED in public CI and still needs an authorized host. Short excerpts,
non-text media, older public refs, Git history, caches and forks remain outside
exhaustive coverage. G15 stays BLOCKED. No force push/history rewrite.

### Scientific evidence: strict value-equivalent numeric integrity

Previously the verifier silently SKIPped absent originals, checked only
shared snapshot numeric paths, ignored numeric ASR repeat fields, and
could overlook duplicate/added candidate IDs. All are now rejected.
Four JSONL receipts: 2+10+10+2 = 24 rows; the snapshot comprises
1883 non-sensitive numeric leaves with an exact matching path set.
Legacy re-serialization of 1.0 as 1 (or 0.0 as 0) is **value-equivalent but
not byte-identical**; bool-versus-int remains a failure.
The comparison is against pre-redaction pinned commit `8c242bae`,
not any new benchmark run. No score/PER was recomputed.

### Test integrity

Removed known always-passing `or True` assertions in security and
worker-path tests. Exercised actual embedded worker symlink guard using
a GPU-free AST execution. New synthetic tests cover the failure cases.
Existing C1 SIGKILL, concurrent-journal and worker-timeout CPU tests remain.

## Release gates and next decision

| Gate | Verdict | Reason |
|---|---|---|
| CPU-only engineering | GO for owner review after exact-head CI | Code/test/evidence changes independent of GPU |
| G1 | PASS | Evaluator dependency freeze receipts populated on host |
| G3 | BLOCKED | Native PyTorch acceptance only 13/14; close() issue |
| G5/G6/G7/G8/G9 | NOT_TESTED | Live-image full A/B and evaluator PER RCA pending |
| G10 | BLOCKED | Real SGLang AR hang/HIP fault remain unexplained |
| G15 | BLOCKED | Historical rights/removal and real dataset release audit pending |
| Publication | NO-GO | Above blocking gates and claim/evidence completeness |

**Operational safety:** This PR does not modify the running machine. Even
after CPU CI passes, do not merge/hot-swap this driver on the active Arm A
worktree. Follow the four-phase `09_POST_ARM_A_SAFE_SWITCHOVER.md` only
after the job has exited and its raw evidence has been independently frozen.

## Documentation/provenance

- Reports 00–09 and early C1 final report retain historical discovery dates.
  This file and the dated addenda are the authoritative *latest* status.
- PR #7 merging means earlier PR #7 BLOCKED-for-approval remarks are stale.
- No upstream PR, GPU experiment, licensed reference ASR comparison, Git
  history rewrite, public audio upload or real dataset Tier 2 scan occurred
  in this independent review.
