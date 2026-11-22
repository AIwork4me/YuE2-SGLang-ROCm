# RC4 M5.1 — Independent Code Review

Scope: every file changed on `mission/w7900-rc4-repro-reliability` vs base
`48d1cb6` (verified PR #16 HEAD), plus review of touched adjacent paths.
Review dimensions: correctness, safety, regression risk, GPU compatibility,
maintainability, error handling, cancellation, bounded retries, provenance,
atomic output publication, no-clobber, benchmark protocol invariance,
licensing/privacy, measurement integrity.

## Defects found (reproduce → root cause → minimal fix → tests)

### D1 (P0, reproducibility) — `scripts/run_smoke_test.sh` stale venv path
- Repro (fresh clone, 2026-11-22 15:30Z): `YUE2_WORKSPACE=… bash scripts/run_smoke_test.sh`
  → `environments/yue2/bin/activate: No such file or directory`, exit 2.
- Root cause: script predated the current workspace layout (`yue2-gfx1100`).
- Fix: resolve venv via `YUE2_VENV` (default `$WS/environments/yue2-gfx1100`),
  repo-relative `phase0_gpu_smoke.py`, `-f` (not `-x`) activate test.
- Verification: re-run → SMOKE PASS on W7900D (receipt in 01_COMMAND_RECEIPTS).

### D2 (P0, wasted GPU work) — `run_wsb.py` under wrong interpreter
- Repro (live, 16:11–16:18Z): driver under host python completed a full
  server-side generation, then finalize failed: `ModuleNotFoundError: orjson`
  (finalize imports `sglang.srt.utils` in-process).
- Root cause: interpreter requirement implicit (only the campaign launcher
  knew it).
- Fix: fail-fast startup guard with actionable message (rc=2) + QUICKSTART
  documents the Env B interpreter.
- Tests: campaign tests stub the driver (unaffected, verified); guard is
  environment-conditional (no GPU/CI impact).

### D3 (P1, false audit failure) — auditor vs torch-driver quarantine convention
- Repro (live): resumed Arm A pilot → `PILOT-INCOMPLETE` with
  `unexpected candidate directory: wsb_000_r0_s831001.partial.quarantine-…`.
- Root cause: torch driver quaranties in place inside `songs/`; SGLang driver
  uses a top-level `quarantine/` dir; auditor knew neither.
- Fix: auditor recognizes `*.partial.quarantine-*` dirs as evidence
  (`quarantined_partials` report field); anything else unexpected still fails.
- Tests: full existing suite green (393 incl. manifest-dependent); live pilot
  now audits PILOT 0 problems with the quarantine recorded.

### D4 (P2, robustness) — `server_identity.py` malformed-receipt crash
- Repro (NC5): forged receipt → `KeyError: 'uid'` traceback (fail-closed but
  unclean exit).
- Fix: required-field validation in `load_receipt` → clean `REFUSED/FAILED
  (code 4)`.

### D5 (P1, isolation) — `fetch_eval_assets_hub.py` hardcoded workspace import
- Root cause: module-level `sys.path.insert(WSB=/data/yue2/…)` — the fresh
  tree's inventory silently came from the ORIGINAL workspace even with
  `--root` set.
- Fix: import path derived from `--root`; plus an offline fast path
  (`SKIP-VERIFIED`) so a stalled mirror cannot block verification of an
  already-complete pinned tree (both behaviors exercised live).

### D6 (P1, scientific reporting) — independent selection keys unfaithful
- See `04_SELECTION_TIE_REVIEW.md`: two analysis scripts carried selection
  keys deviating from the official frozen 4-tuple; prompt-19 divergence
  reproduced and eliminated.
- Fix + tests: `tests/test_selection_tie_semantics.py` (5 tests, incl. the
  frozen 192/192 identity check and a mutation control).

### D7 (P2, docs) — QUICKSTART gaps that break real reproduction
- TMPDIR omission (pip `/tmp` exhaustion — reproduced), HF env overrides
  (reproduced, NC8), smoke venv name (D1), driver interpreter (D2).
- Fix: QUICKSTART §0 notes + Path B driver line; each backed by a live
  failure+fix receipt.

### D8 (P3, tooling) — `rc4_memory_lifecycle.py` CSV fieldnames union bug
- 5 measurement cycles completed; CSV write crashed on heterogeneous keys.
  Fixed (union fieldnames); data recovered from stage prints; noted in the
  CSV.

## Reviewed-but-not-changed (with reasons)

- `run_wsb_torch.py` resume/identity/quarantine logic: correct under live
  interruption (twice exercised); no change.
- Frozen-evidence paths and official evaluator: untouched (protocol
  invariance).
- `gpu_lock.py`: contention behavior verified live (bounded timeout, holder
  identity, no preemption); no change.
- Server lifecycle in ad-hoc pilot scripts: RC4 scripts all carry
  identity-verified stop traps; in-repo pilot-with-server wrapper queued as
  follow-up (R1-L1), not snuck into this branch.

## Regression & gate runs (this session)

- CI-scope suite: **367 passed / 0 failed / 26 skipped** (honest manifest
  skips) — same command as CI (`--ignore` the 3 hardware-dependent files).
- With workspace: +26 manifest-dependent tests → 393 passed total.
- `tests/test_c2_provenance.py` 35/35; selection-tie tests 5/5;
  evidence guards tier-1 + tier-2 PASS; `compileall` on changed scripts;
  `bash -n` on changed shell; `git diff --check` clean.

## Licensing/privacy review of the diff

No lyrics, transcripts, audio, model weights, secrets or private paths in
the diff; fixtures numeric-only; guards re-run PASS on the final tree.
