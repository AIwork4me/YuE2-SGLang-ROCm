# M1 — Integration, CI and Engineering Freeze (YUE2-AMD-JOINT-BLOG-RC)

Status: **COMPLETE (engineering); independent review PENDING (Draft PRs #14/#15)**

Branches:
- `mission/joint-blog-rc-m1` = PR #13 HEAD `f7fda39` + 3 fix commits → PR #14 (Draft)
- `integration/joint-blog-rc` = the above + merged #12 stack + #8 reconciliation + #7 doc restoration → PR #15 (Draft)
- Live campaign checkout fast-forwarded `f7fda39` → `fee027d` (= PR #14 head) at
  2026-11-19T01:25Z **with owner authorization**, during the supervisor's retry-sleep
  window; no process was restarted.

---

## M1.1 — PR #13 CI failures (5× TestScoreGate `PermissionError: '/data'`)

Root cause (code-verified, not guessed): `scripts/gpu_lock.py` froze
`DEFAULT_LOCK` from `YUE2_WORKSPACE` at import; `mission_chain.score()` called
`gpu_ownership()` without an injected path; on CI (non-root, no `/data`)
`path.parent.mkdir(parents=True)` → `PermissionError: '/data'`
(run 44421080608). Exactly the anticipated defect class: module-level path
constant + fixture monkeypatches only `mission_chain.WS`.

Fix (minimal, dependency-injectable):
- `gpu_lock.resolve_default_lock()` — call-time resolution everywhere
  (library + CLI); import-time constant kept only as documented legacy alias.
- `mission_chain.score()` — lock derived from the chain's own `WS`
  (injection); lock `TimeoutError` now fails the gate (log + return False)
  instead of crashing the supervisor — a lock failure can never yield a
  successful score gate.

Tests: call-time env resolution (library + CLI + workspace fallback);
lock-unavailable → gate FAIL + evaluator never launched (real cross-process
flock holder); score() locks WS/gpu.lock (spy). Required matrix covered:
rc0+complete passes; rc0+incomplete fails; rc≠0+complete fails; missing
summary fails; partial outputs quarantined (moved aside, never deleted);
non-root / no-`/data` = the CI environment itself.

Additionally repaired 18 dormant tests (they only execute on a
manifest-equipped host; CI skips them): workspace propagation to the auditor
subprocess; self-consistent identity bundles; current auditor vocabulary.

**Suite: 190 passed / 0 failed / 0 skipped** (manifest-equipped host).
CI expectation: red → green (the 5 failures fixed; skips remain honest).

## M1.2 — Arm B server lifecycle (P0 defects)

All five defects were REPRODUCED with real-subprocess tests before fixing:

| # | Defect | Live evidence | Fix |
|---|---|---|---|
| 1 | `LOG` env collision: callers exported `LOG=<dir>` into `serve_yue2_gfx1100.sh` which reads a FILE → server died at boot | boot log 2026-11-18T23:55Z `line 45: /data/yue2/logs: Is a directory` | serve script uses `SERVER_LOG` (dir-valued legacy LOG ignored); callers use `LOG_DIR` |
| 2 | `trap stop_server EXIT` followed by `exec` into `gpu_lock.py` → trap discarded → SGLang server orphaned on EVERY driver exit | code inspection + scenario tests | launcher keeps ownership: gateway runs as foreground child (background + interruptible `wait`), EXIT/INT/TERM traps live for the whole campaign, signals forwarded |
| 3 | `capture --run-state` expects a DIRECTORY; both callers passed a FILE path → receipt nested one dir too deep → every verify/stop "receipt missing" | live 23:25Z rc=1 + `debug_server_receipt.json/` dir in logs | callers pass `RECEIPT_DIR` |
| 4 | `RUN_ID` never exported → inner `bash -c` expanded `--run-id ""` on every fresh launch | `test_10_restart` caught it; original code inspected | exported |
| 5 | health poll interval (10s) ≥ bounded timeout → single-probe degradation | analysis | `ARMB_HEALTH_POLL_S` (default 5) |

Real music-generation acceptance added (`campaign_ops/armb_acceptance_request.py`):
bounded full-pipeline `/v1/audio/generations` request with ORIGINAL smoke lyrics
(non-protocol parameters labeled as such), audio must decode, be ≥5 s,
non-silent; SHA256 receipt. `/health` + `/v1/models` no longer suffice.
Stop failure escalates exit codes (never hides behind rc=0); cleanup only ever
targets the VERIFIED identity receipt.

**Tests (`tests/test_armB_lifecycle.py`, 16 scenarios, all 10 mission cases):
driver success/failure ×2, health timeout (bounded, no orphan), boot death,
identity-capture failure (fail-closed: unverifiable server is never signaled),
SIGINT/SIGTERM (verified server stopped, exit 128+sig), stubborn server
(SIGINT+SIGTERM ignored → refusal, operator escalation, no SIGKILL), forged
receipt (refused, real server untouched), competing launchers (flock no-op),
gpu-lock contention (bounded), restart/resume (run_id reuse), acceptance
generation success/failure.**

## M1.3 — Archive restoration & scoring gates

`extract_archive_safe.py` hardened:
- `--expect-sha256` pin now ENFORCED (exit 6 on mismatch); digest in receipt.
- Staged extraction + atomic rename: a crash can never leave a partial
  `<dest>`; failed-attempt staging preserved for inspection, never
  auto-deleted, never blocks retry.
- Truncated-tar-in-valid-gzip surfaces at extract time (staging kept).

Verified present (from #12/#13 lineage, now covered by merged tests):
restoration content-identity audit with subset semantics (never FULL),
partial scoring outputs moved aside (never deleted, never re-run complete
summaries), stdout/stderr archived per attempt, idempotent chain recovery,
durable journal with torn-tail quarantine, fail-closed interior corruption.
C2/C2.1 summary-identity binding (inputs/evaluator/results) arrived with the
#12 merge and is enforced by `verify_provenance.py` + 100+ tests.

## M1.4 — PR chain reconciliation

Topology (verified): `main` ← #7(merged); `feat/yue2-rocm-publication-readiness`
← {#8, #9}; #9 ← {#10→#11→#12 stack (34 commits), #13 (11 commits)}.

- Base = #13 lineage + M1.1–M1.3 (PR #14).
- Merged #12 (`aa3f34f`): 2 conflicts (both sides had independently fixed the
  same dormant tests) → took richer #12 versions, re-added M1.1 regressions.
- PR #8: implementation superseded (diverged `run_wsb_torch.py`; the
  integrated lineage is the one that completed the fresh 384/384 Arm A run).
  Guarantees ported as tests (torn tail, last-status-wins, incomplete-tail
  refusal, interior-corruption fail-closed). Stale doc snapshots not carried.
  **Recommend closing #8 as superseded after review.**
- PR #7 restoration: `docs/PUBLIC_EVIDENCE_REDACTION.md` restored from main
  (lineage predated the merge); `public_evidence_guard.py` + tests identical
  to main and PASS on the integrated tree.

**Integrated suite: 355 passed / 0 failed / 0 skipped; compileall + bash -n
clean.** Draft PR #15 opened against `fix/w7900-fresh-image-resume-hardening`
(not main). No protocol locks, campaign identities, archive identities, or
evidence attribution changed.

## M1 acceptance checklist

- Exact integrated HEAD pinned: `0a913b0` (PR #15) — YES
- CPU CI green: local 355/0/0; GitHub CI on PRs #14/#15 — **PENDING (runs triggered by push; verify before R1)** 
- No unjustified skips: skips are manifest/GPU-dependent only — YES
- P0 concurrency/lifecycle defects fixed: 5 defects + tests — YES
- No sensitive evidence regression: public_evidence_guard PASS — YES
- Protocol locks unchanged — YES
- No running campaign disturbed: live tree updated only in the sleep window
  with owner authorization; supervisor PID 3363794 untouched — YES
- Independent code review: **PENDING — Draft PRs #14/#15 await owner review**

## Handoff note (live behavior after fast-forward)

The supervisor's next `armB_acceptance` retry reads the fixed scripts from
disk. On pass, the chain advances to `armB_campaign` and launches the full
Arm B fresh campaign (days of GPU, single-tenant via gpu_lock). Monitor:
`tail -f /data/yue2/logs/mission_chain_console2.log`.
