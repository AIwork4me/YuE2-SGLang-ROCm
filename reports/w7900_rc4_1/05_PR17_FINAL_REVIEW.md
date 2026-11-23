# RC4.1 — PR #17 final review (M6.4)

Reviewed: PR #17 (mission/w7900-rc4-repro-reliability @ 16f2504, base
mission/joint-blog-rc2, OPEN/DRAFT, both cpu workflows SUCCESS on the
exact head) + RC4 report set + RC4.1 findings.

## Does RC4.1 fix PR #17's follow-up defects?

| RC4 follow-up (PR #17 §J) | RC4.1 status |
|---|---|
| 1. R1 upstream root cause: minimal reproducer + upstream issue | Reproducer COMPLETE (02_IDLE_SPIN_REPRODUCER.md, code-level location at scheduler.py event_loop); upstream issue NOT submitted (owner-authorization rule) — remains open |
| 2. In-repo pilot-with-server wrapper (R1-L1 closure) | DONE: scripts/campaign_ops/run_with_server.sh + 5 lifecycle tests + live proof (phase B1 ran through it end-to-end on W7900) |
| 3. Repeated-tags hang: minimized payload + fix/upstream report | DONE: root-caused to test-harness budget (NOT a server defect); bounded precheck + matrix fixes + hardware proof both budget regimes |
| 4. PER cross-evaluator parity (G4) | UNCHANGED: BLOCKED_EXTERNAL (needs authorized CUDA host) |
| 5. Independent third-party reproduction | NOT_PRESENT (external executor required) |
| 6. Author/AMD approval | NOT_PRESENT |

Additionally RC4.1 fixed PR #17-adjacent evidence debt: 786→791
reconciliation, missing CSVs committed, unit mislabels, stale verdicts,
README staleness ("native pending" since RC3).

## Unresolved P0/P1 in PR #17 itself

None open at project level: RC4's P0s (smoke venv, wrong-interpreter
finalize) and P1s were fixed within PR #17 with regression tests; the
runtime P0/P1 blind spots (dead-scheduler health, silent-degradation
risk, lock discipline) are what RC4.1 closes on the stacked branch.

## Merge-order recommendation (OWNER DECISION — not automated)

1. PR #16 (mission/joint-blog-rc2 → integration/joint-blog-rc) first —
   it is the base of PR #17; CI green at its head per PR page.
2. PR #17 second (base unchanged; exact-head CI green).
3. RC4.1 stacked PR (base mission/w7900-rc4-repro-reliability) last.
   Alternatively the Owner may rebase RC4.1 after #17 merges — the branch
   adds no conflicts by construction (no shared-file edits with #17's
   frozen-path scripts; doc files amended additively with snapshot
   annotations).

## Consistency checks performed

- PR #17's reports vs actual CSV: 2 stale claims found (786; armA n=2) —
  fixed in RC4.1 with amendment annotations; original mid-run text
  preserved in git history.
- PR #17's self-reported lock-scope defect (R1-C1): RC4.1 sessions all
  held the lock continuously (03_LOCK_OWNERSHIP.md).
- Frozen Arm A/B evidence: byte-identical before/after RC4.1.

## Verdict

PR #17 remains MERGEABLE from the engineering side once the Owner accepts
its documented residuals (R1 upstream, PER parity external). RC4.1 closes
the actionable follow-ups and strengthens the evidence layer; recommend
merging in the order above. No unauthorized merges performed.
