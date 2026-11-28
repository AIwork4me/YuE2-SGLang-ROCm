# INDEPENDENT_REVIEW.md — RC6 §7.3 adversarial review

Conducted by a skeptical third-party-maintainer persona over the RC6 branch
state. AI review ≠ human maintainer review — this is an internal adversarial
audit, honestly labelled; no external human has reviewed RC6.

## Scientific reviewer

**Are the comparisons fair?**
- 2×2 PER attribution: same 384 audios, receipt-level audio_sha cross-match
  384/384 (A2 audit) — fair. Cells re-derived from frozen receipts with
  bootstrap CIs. OK.
- Scoreboard B: same frozen evaluator (verify_release/verify_assets gates
  ran inside the driver), same audio bytes, official summarize — the ONLY
  variable is the selection set, disclosed everywhere. OK.
- Q3O: never compared against official numbers without the
  ROCm-adapted label + tie-rate disclosure. OK.
- One caveat kept honest: Scoreboard B was computed by an RC6 driver that
  reuses the evaluator's own code but is NOT the evaluator's `score` CLI
  path (standard mode requires 384 rows). The driver runs
  verify_release/verify_assets/prepare_inputs/identity/workers/read_cached/
  summarize verbatim; receipts are identity-hashed by the evaluator's own
  `extended_eval.identity`. Disclosed in the driver docstring and in
  03_CORRECTED_SCOREBOARD.csv notes. RESIDUAL RISK: low, but a purist could
  ask for the same aggregation through `wsb_eval.py score --per-results`;
  that path is impossible for a non-official per arm (reuse_per validates
  evaluator-produced per receipts only) — which is itself the honest reason
  the driver exists.

**Are claims supported?**
- Checked spot-wise: every number in SCIENTIFIC_EVIDENCE_CLOSURE.md traces
  to a JSON/CSV receipt file re-derived in RC6 (determinism 380/384;
  attribution cells; scoreboard B; performance percentiles recomputed from
  the raw CSV; lifecycle timings from receipts).
- PCM claim discipline: the 4 divergent candidates are NEVER claimed
  identical; unverifyability is stated in caps-constant form. OK.

**Are the evaluation arms separate?** Yes — different files, engine
identities audited, no mixing; classify() refuses metric mixing.

**Overstated conclusions?** The one place I pushed back in drafting: "8.4488%
vs paper 8.44%" must never be read as official-evaluator parity. The
verdicts keep `OFFICIAL_SCIENTIFIC_EQUIVALENCE_VERDICT = NOT_ESTABLISHED`
and the author package asks for exactly the CUDA control. Kept.

## Runtime reviewer

- GPU actually used? GPU_EXECUTION_VERIFIED receipts in every session
  (physical BDF chain); first-song lifecycle CLEAN end-to-end; no orphan
  processes; lock released after every session (checked live after each).
- Timeouts/shutdown bounded? Lifecycle receipts show bounded steps; a
  surviving-server case ends BLOCKED and refuses later GPU work (RC4.1/RC5
  design, unchanged). The stale-lock control proved dead-holder takeover.
- Lock correctness? Single-owner flock with pid+starttime+cmdline;
  atomicity fix (cleanup before release) retained; live negative control
  passed. One residual: the lock file is on the workspace volume — a
  workspace-volume loss orphans lock state; harmless (stale detection) but
  worth noting.
- Resources reclaimed? Yes (drain→stop→tree→port→gpu receipts).

## Developer reviewer

- First song from a clean checkout? Done live (Mode 2) — with 6 real
  frictions, all fixed and re-verified; the friction log is the evidence.
- Commands complete? The canonical quickstart + CLI help were re-checked;
  CWD-independent patch paths verified.
- Error messages useful? Fail-closed exits carry reasons (REJECT taxonomy,
  ScorerValidationError messages, gpu_identity reason strings).
- Can I verify my own result? Yes — verify tool with verdict vocabulary;
  the tool demonstrably FAILS when identity is unverifiable (pre-fix
  failure recorded as control evidence).

## Open-source maintainer reviewer

- Diff minimal? RC6 adds tools/docs/tests and hardens two scripts (math
  untouched, GREEN regression); no refactors of reliable internals; frozen
  evidence untouched (0/13,859 mismatches post-mission).
- Dependencies pinned? Yes (lock files + runtime manifest + pins).
- Maintainable? MAINTENANCE_SCHEMAS + UPSTREAM_PATCH_OWNERSHIP define
  update procedures and per-issue upstream destinations.
- Upstream boundaries clear? Yes (PR snapshot pinned; absorbed patches not
  reapplied; unmerged status stated everywhere).
- Hidden license risks? Public evidence guards PASS; original first-song
  lyrics created for the repo (publishable); historical Git objects remain
  un-scanned by the working-tree guard (disclosed, inherited; merge-time
  gate recorded).

## Verdict

APPROVED_FOR_RELEASE_CANDIDATE with the residual risks above stated (none
blocking; all disclosed in the ledger). This review does NOT substitute for
author/AMD/third-party review — those remain external gates.
