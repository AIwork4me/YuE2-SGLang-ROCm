# RC2_01 — Independent Engineering Review of PR #15 (integration/joint-blog-rc @ 66b5a13)

**Reviewer:** AI second-pass independent review (opencode session, GLM)
**Scope limitation (honest):** this is an AI-driven review, executed in a
separate worktree with exact-HEAD tests, fault injection and mutation
controls. It is **not** a human independent approval and must not be
presented as one. Owner/human review of PRs #14/#15 remains open.

**Worktree:** `/tmp/opencode/rc2` @ `66b5a13` (PR #15 head), clean base,
campaign checkout never touched. All execution CPU-only, in the reviewer
worktree or isolated tree copies.

---

## 1. Review method

1. Line-by-line review of the runtime/lifecycle/provenance surface:
   `gpu_lock.py`, `mission_chain.py`, `server_identity.py`, `driver_alive.py`,
   `run_wsb.py`, `run_armB_campaign.sh`, `armB_acceptance.sh`,
   `armb_acceptance_request.py`, `serve_yue2_gfx1100.sh`,
   `extract_archive_safe.py`, `atomic_publish.py`,
   `verify_wsb_artifacts.py`, `public_evidence_guard.py`,
   `verify_provenance.py` (key paths).
2. Exact-HEAD suite on the manifest-equipped host: **373 passed / 0 failed**
   (one process, CI scoping; 355 at base + 18 new regression tests; the 3
   environment-dependent files excluded exactly as CI does — see §5).
3. Pre-registered mutation controls (`mutation_controls_c21.py`): **5/5
   KILLED**.
4. **16 new adversarial mutations** written by this review across lock
   resolution, score gating, journal semantics, archive SHA enforcement,
   no-clobber publication, stop-path re-verification, guard vocabulary,
   zombie liveness, audit bar: **11 killed by the existing suite; 5 survived
   → all 5 now pinned by new tests and re-verified killed** (§3).
5. `compileall` clean; `bash -n` clean for all `scripts/*.sh`;
   `public_evidence_guard.py` PASS on the reviewed tree.

## 2. Verified-correct behavior (spot list)

- **gpu_lock**: flock is authoritative; call-time path resolution everywhere
  (import-time constant is a documented legacy alias only); zombie-aware
  holder liveness; stale-receipt-under-live-flock waits loudly; release
  writes a released receipt; stop never SIGKILLs.
- **mission_chain**: single-instance flock; audit verdict parsed from
  `audit.json` (exit code AND file); score gate requires rc=0 AND
  `summary.complete`; complete summaries never re-run; partial outputs
  moved aside and preserved; lock injected from the chain's own WS with
  lock-timeout = FAIL.
- **Arm B lifecycle**: launcher keeps traps (no exec past them); gateway is
  an interruptible foreground-child; stop only via the VERIFIED identity
  receipt (pid/uid/starttime/argv-sha/port-ownership re-checked before EVERY
  signal); stop failure escalates the exit code; acceptance requires REAL
  bounded music generation with decodable, non-silent, ≥5 s audio and a
  SHA256 receipt.
- **Journals/archives**: fsync'd appends; write-once `evaluation_inputs`;
  immutable `run_config` (mismatch = exit 3); quarantine-not-delete;
  staged extraction + atomic rename + enforced SHA pin + no-clobber;
  `RENAME_NOREPLACE` with fail-closed fallback.

## 3. Defects found (with fixes on this branch)

### P1-1 (fixed) — resume status invisible to the chain advancement gate
`run_wsb.py` journaled resumed-but-verified candidates as
`"complete(resumed)"`, while `mission_chain.journal_complete()` counted
exact `"complete"` only. After a journal-tail loss with surviving artifacts
(the crash-recovery scenario the design advertises), the chain would
relaunch the driver every 600 s forever, each pass appending another 384
`complete(resumed)` rows, never advancing to audit. Arm A's driver
(`run_wsb_torch.py`) already did this correctly — Arm B diverged.
**Fix:** emit `status="complete"` + `"resumed": true` (mirrors Arm A) AND
make `journal_complete()` accept the `complete` prefix (backward-compatible
with any historical `complete(resumed)` rows). Regression tests:
`TestJournalCompleteCountsResumed`, `test_resume_journals_exact_complete_status`.
Mutation-killed: F1, F2.

### P1-2 (fixed) — live-server test suite was default-ON, not opt-in
`tests/test_server_yue2_rocm.py` documented itself as opt-in but defaulted
`SERVER=http://127.0.0.1:31000`. Consequence (demonstrated live during this
review, involuntarily): a plain `pytest tests/` on the benchmark host
mid-campaign sends generation traffic to the frozen campaign server — a
protocol-interference hazard and a mission §1.1 violation by default.
**Impact of the review-time incident (disclosed):** two bounded contacts
(≤7 min wall each, small smoke budgets); campaign verified unaffected
afterwards — 0 failed candidates, 0 retries, wall-times nominal (22/22 →
22/22 complete across the window; supervisor cadence uninterrupted).
**Fix:** module skips unless `SGLANG_TEST_SERVER` is set, and additionally
refuses while a GPU-ownership lock is held (override requires an explicit
env). Contract tests: `tests/test_live_server_optin.py` (behavioral skip
+ source-contract, network-free). Mutation-killed: F3.

### P2-1 (fixed) — unbounded scoring execution and unbounded stage retries
`score()` had no subprocess timeout: a hung evaluator would hold the stage
and the GPU lock forever. `audit()`/`run_armb_acceptance()` let
`TimeoutExpired` propagate, killing the supervisor (restartable, but the
chain should degrade, not die). Scoring stages retried every 1800 s with no
cap on GPU-heavy attempts.
**Fix:** `YUE2_SCORE_TIMEOUT_S` (default 6 h) with evidence-preserving
timeout handling; all three subprocess sites degrade to FAIL-and-retry;
`score_stage()` bounds attempts at `YUE2_SCORE_MAX_ATTEMPTS` (default 8),
escalates to `blocked_reason` with reset instructions, resets on success.
Tests: `TestScoreBoundedExecution`, `TestScoreStageRetryBounds`.
Mutation-killed: F7, F8.

### P2-2 (fixed) — mutation-surviving invariants (test-coverage gaps)
Three security/reliability invariants could be silently broken with the
suite staying green: (a) removing `"lyrics"` (or any key) from the guard's
FORBIDDEN vocabulary; (b) deleting the per-signal re-verification in
`server_identity stop`; (c) replacing the renameat2 fail-closed fallback
with a clobbering `os.rename`.
**Fix:** pinned by `test_forbidden_vocabulary_is_pinned` +
`test_every_forbidden_key_is_flagged` (fixed expected set, not
self-referential), `tests/test_server_identity_reverify.py` (2 tests),
`TestRenameat2UnsupportedFailsClosed`. Mutation-killed: F4, F5, F6.

### P3 (fixed, minor) — disk-guard loop scope; partial-dir collision
The disk-space guard broke only the inner candidate loop (manifest spam
across all remaining prompts); the move-aside name could collide on a
same-second retry (nesting into the existing dir). Fixed: `STOP` +
`stopped_by_disk_guard` summary field; pid-suffixed aside names.

### P3 (fixed, host-specific, pre-existing) — cross-file test pollution
On a manifest-equipped host, `test_restoration_audit` (real frozen
verifier) runs before `test_wsb_resume` in one process; `sys.modules`
caching then defeats the latter's stub verifier → 2 failures that never
appear in CI (no /data) or per-file runs. Verified pre-existing at `66b5a13`
(stash/repro). **Fix:** cache-purging autouse fixture + realistic stub.

### Observations (no change required; documented)
- `gpu_lock stop --yes` signals the gateway python; CPython's
  `subprocess.run` SIGKILLs the direct bash child, skipping its cleanup —
  the CAMPAIGN path is safe (launcher EXIT trap performs identity-stop), the
  ACCEPTANCE path relies on its inner traps which SIGKILL bypasses; bounded
  by `mission_chain`'s acceptance timeout path now degrading cleanly. Driver
  orphans after gateway kill exit on server-loss (bounded retries).
- `detect_platform()` recorded `"gpu": "unknown"` in the live Arm B
  `run_config.json` (rocm-smi CSV parse) — cosmetic provenance gap; hardware
  identity is pinned elsewhere (host inventory + identity chain).
- `gpu_lock.status()` can false-negative `held` on OSError — monitoring-only.

## 4. The PR #14 + PR #12 combination question (mission-critical)

Verified on the merged tree, not on descriptions: the #12 stack's richer
implementations (provenance, no-clobber, resume verification) coexist with
#14's M1.1–M1.3 fixes (call-time lock resolution, lifecycle, archive SHA
enforcement); the merge-conflict resolution (2 files, both sides fixing the
same dormant tests) preserved both behaviors — confirmed by the passing
matrix above and by mutation controls killing mutations on both lineages'
invariants. The 4 commits on `main` not in PR #15 are exactly the PR #7
security merge, content-identical (blob-level) in #15 — no unreconciled
semantic divergence (RC2_00 §3).

## 5. Exact-HEAD CI evidence

- Local manifest-host suite (this review, one process): **373 / 0 / 0**
  with CI scoping. Environment-dependent files excluded exactly as CI
  excludes them: `test_yue2_rocm_fallbacks.py` (needs env-B python with
  sglang), `test_first_audio.py` (needs legacy `/data/yue2/runs/phase4`
  artifacts absent on this fresh image), `test_server_yue2_rocm.py`
  (live-server, now correctly opt-in).
- GitHub CI on PR #15 @ `66b5a13`: run 44442680950, cpu job PASS
  (327 passed / 28 skipped). **Note:** the "355 passed / 0 skipped local"
  claim in prior reports is reproducible only under the same scoping; the
  honest phrasing is "355 (CI-scoped) + environment-dependent files excluded
  by CI design". This review's 373 uses identical scoping plus the new tests.
- Public evidence guard: PASS. Tier-2 real-dataset scan: re-run in M6
  posture (PASS there); working-tree guard re-verified PASS here.

## 6. Verdict

**PR #15 engineering quality: PASS with conditions.** No open P0/P1 defects
remain in the reviewed scope **after this branch's fixes** (5 defects fixed:
2×P1, 2×P2, 3×P3-class). The base `66b5a13` alone carries P1-1/P1-2 → the
fix commits on `mission/joint-blog-rc2` (Draft PR) should be reviewed and
folded into the RC before G1 can be declared. Deployment to the live
campaign checkout is owner-gated and recommended only at a stable window
(fixes are backward-compatible with the running campaign's journal format:
new rows use plain `complete`; the counter prefix accepts both spellings).
