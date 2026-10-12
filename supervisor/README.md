# Completion Supervisor — safe autonomous finish for the gfx1151 WSB run

## Components

- `complete_benchmark.py` — the supervisor. Detached via `setsid` (own
  session; immune to process-group cleanup; adopted by systemd on parent
  death). flock-protected (`supervisor.lock`), state machine in
  `state.json`, durable log `logs/supervisor.log`, poll every 10 min.
- Durable keeper — a recurring workspace automation ("YuE2 supervisor
  keeper", every 30 min) that verifies the supervisor is alive and relaunches
  it (idempotent) if it died, unless state is `SCORING_COMPLETE`. This
  survives application restarts; the setsid process survives shell/session
  exits. Machine reboot is the only event that stops both — after a reboot,
  run this once:
  `setsid /home/amd/Desktop/YuE2/environments/yue2/bin/python /home/amd/Desktop/YuE2/supervisor/complete_benchmark.py >> /home/amd/Desktop/YuE2/logs/supervisor.log 2>&1 < /dev/null &`

## Guarantees

- Read-only toward the live experiment: no generation-parameter changes, no
  candidate interruption, no auto-restart of a failed generation.
- Scoring begins only when ALL gates pass: (A) driver AND milestone watcher
  processes have ended, (B) strict full-mode auditor exit 0, (C) 384/384
  verified via the official `verify_result`, (D) 192 prompts × 2, (E) zero
  unresolved problems, (F) evaluator frozen-release hashes + venvs + models
  verified, (G) ≥20 GiB GTT free and ≥16 GiB RAM available.
- Any gate failure ⇒ no scoring, evidence preserved, blocker recorded in
  `state.json` + `gate_report.json`.
- After scoring, an automatic CROSS-VALIDATION stage independently recomputes
  and cross-checks the official results (coverage 384/192, the exact official
  min-key PER selection incl. phoneme tie-break vs the evaluator's recorded
  selection, PER micro aggregates, SongBench dimension means from raw
  receipts — 4-decimal rounding tolerance — and additional-metric coverage
  + selected-set identity). Any mismatch => BLOCKED_CROSSVAL_MISMATCH, no
  evidence commit of results as final. Output: supervisor/cross_validation.json
  (copied to evidence/).
- Scoring is retry-safe: completed score outputs are skipped idempotently;
  incomplete attempts are moved aside (`*.attempt_<ts>.bak`), never
  overwritten silently.
- Evidence commits go to `main` only; `validation/gfx1100-rocm7141`
  (W7900 team, internal PR #1) is never touched; pushes are verified against
  the remote SHA before being logged as pushed.
- No Q3O (platform-blocked, previously recorded as NOT RUN).
- Scoring never overlaps generation: gate A requires both generation
  processes gone first.

## What the supervisor does NOT do

The final three-role reviews, the H800 comparison narrative and the upstream
report fill (mission Phase 5 beyond scoring) require a full model session —
the supervisor stops at `SCORING_COMPLETE` with evidence committed and
pushed. This is a stated limitation, not an automated step.

## Known watcher gaps (documented, deliberately not hot-fixed)

The live `milestone_watcher.sh` (bash must not be edited mid-run) has four
known gaps the supervisor supersedes: it stops at 384 without scoring; it
counts `result.json` files instead of official verification; its push-retry
loop can log "pushed" after failed attempts; it commits with `git add -A`
in its worktree. The supervisor waits for the watcher to exit before
touching that worktree, performs verified pushes, and stages only enumerated
files.
