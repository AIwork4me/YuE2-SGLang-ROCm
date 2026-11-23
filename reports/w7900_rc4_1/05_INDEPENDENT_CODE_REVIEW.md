# RC4.1 M5.4 — Independent code review (AI reviewer, second pass)

Scope: full diff 16f2504..HEAD on
`mission/w7900-rc4-1-fail-loud-health-evidence` (41 files, +3,639/−48).
**AI_INDEPENDENT_REVIEW — this is NOT a human-maintainer approval.**

## Frozen-path invariance verified

`scripts/gpu_lock.py`, `scripts/server_identity.py`, `scripts/run_wsb.py`,
`scripts/run_wsb_torch.py`, `patches/*`, evaluator tree: ZERO diff vs
16f2504 (git diff empty for those paths). The official WSB protocol path
is untouched; `input_budget` is deliberately not wired into it.

## Findings (self-review, adversarial pass)

### F1 (fixed during review) — run_with_server.sh exec-past-traps
First implementation `exec`'d into gpu_lock.py, which would discard the
wrapper's signal traps (same defect class fixed in run_armB_campaign.sh)
— caught by test_4 (SIGTERM cleanup) hanging; rewritten to the
gateway-background + trap-owning pattern; signal cascade to the wrapped
command via inner-pid file. All 5 lifecycle tests green.

### F2 (fixed during review) — INNER_PID_FILE not exported
Signal cascade initially targeted an empty pid file; caught by the same
test; fixed + re-run.

### F3 (fixed during review) — readiness positive-control weakness
Mutation M10 exposed that the row-count check accepted the number
anywhere; now pinned to the canonical claim forms. Mutation M7 exposed an
operator-precedence bug (`A and B or C`) in the new timeout test. Both
closed; 12/12 mutations KILLED.

### F4 (accepted, documented) — PCI BDF best-effort on multi-GPU hosts
`gpu_identity` BDF detection falls back to scanning /sys/class/drm for
the amdgpu node (this torch build does not expose PCI attrs via device
properties). On a MULTI-GPU host the fallback could bind to the wrong
card; the arch check remains the primary identity gate. Documented here;
single-GPU rig (this project's target) is unaffected. Negative control
(wrong expected BDF → mismatch rc3) verified on hardware.

### F5 (accepted) — readiness BUSY exit code is 0
BUSY is a healthy state (generation in flight); run_with_server accepts
READY or BUSY before running its command. Progress-deadline escalation
(exit 6) exists for callers with progress files.

### F6 (verified) — no new CPU-fallback surface
gpu_identity is the only new torch-touching code; it PROBES the GPU and
fails loud; no code path selects CPU implicitly. The test-suite stub uses
the sanctioned `YUE2_ALLOW_CPU=1-I-AM-A-TEST` token (CPU_TEST_MODE
semantics, never GPU PASS).

### F7 (verified) — resource release
All GPU sessions: lock released (receipts), servers identity-stopped,
port freed, VRAM back to 28,028,928 B baseline; orphan scan clean at
mission end. The B2 operator ladder (SIGTERM→SIGKILL) was applied ONLY to
the session's own verified-identity pid after the graceful stop refused
(rc 3) — no foreign process was signaled anywhere in this mission.

### F8 (verified) — evidence honesty
Raw CSV untouched; aggregates regenerated only via the declared-method
flag; frozen trees hash-identical (15,825 files); mission's own failed
native attempts remain journaled as `failed` rows (not hidden); the
two preserved RCA wavs are CC BY-NC model outputs and stay host-side
(NOT pushed).

## Residual risks

1. Upstream scheduler defects (idle spin; no respawn on worker death)
   remain — project mitigations documented, upstream fix pending owner
   authorization (02_IDLE_SPIN_REPRODUCER.md).
2. The RC4 CPU-fallback suspect stays SUSPECT_UNCONFIRMED (mechanism);
   recurrence would now be loud but the original incident is unproven.
3. gpu_identity probe adds a tiny GPU op at session boundaries —
   negligible (256² fp32 ≈ 768 KiB); no normal-path generation overhead.
4. readiness's scheduler signature match ("sgl_diffusion"/"scheduler")
   is stack-specific; if upstream renames the worker the check fails
   CLOSED (WORKER_DEAD), never false-READY — safe direction.

## Regression evidence

- CI-scope suite: 425 passed / 0 failed / 26 honest manifest skips
- workspace-dependent: +33 passed (run with YUE2_WORKSPACE=/data/yue2)
- mutation controls: 12/12 KILLED
- public-evidence guard + lyrics detector: PASS on final tree
- compileall + bash -n: clean
- real-W7900 phases A/B1/B2/C: all verdicts true (see FINAL_REPORT_ZH)
