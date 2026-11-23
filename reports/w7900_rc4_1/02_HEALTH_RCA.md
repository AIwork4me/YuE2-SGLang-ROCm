# RC4.1 M2 — Health RCA: HTTP_HEALTH ≠ GENERATION_READY

## 1. Reproduced blind spots (RC4 evidence + RC4.1 re-verification)

1. **Dead scheduler invisible to /health** — RC4 fault injection
   (rc4_evidence/mini_window/sigkill*.json): scheduler SIGKILL → in-flight
   request hangs to client timeout, /health stays 200, no respawn.
   RC4.1 re-verified with the NEW tooling (phase B2, real W7900): after
   scheduler SIGKILL, `/health` = 200 while `server_readiness.py check`
   returns **WORKER_DEAD** (exit 3) — the blind spot is now detected at
   project level without touching upstream SGLang.
2. **Half-shutdown** — SIGINT stop can hang in "waiting for background
   tasks"; `server_identity.py stop` correctly refuses (rc 3). RC4.1 keeps
   the documented recovery ladder (SIGTERM → operator decision); the B2
   receipt records the ladder outcome and VRAM release.
3. **R1 idle busy-loop** — deterministic re-reproduction this mission
   (phase B1): after one clean request, 90 s idle sample → **9145 CPU
   ticks = 102% of one core** (RC4: 9127/101%). GPU util 0%.

## 2. Upstream root cause located (code-level)

`sglang/multimodal_gen/runtime/managers/scheduler.py` (commit
ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f + repo patchset), `event_loop()`
lines ~1314-1325:

```python
items = self.get_next_batch_to_run()
if not items:
    if self.waiting_queue and self._dynamic_batching_enabled():
        ...
        self._poller.poll(timeout=remaining_ms)   # sleeps ONLY when work is waiting
    continue                                     # idle + empty queue: tight spin
```

When `waiting_queue` is empty and no batch is runnable, the loop
`continue`s with **no poll timeout and no sleep** — a busy spin at 100% of
one core for the entire idle lifetime of the server. The RC4 8.7-hour
orphan (R1-E1) is this loop running for hours. This is an UPSTREAM defect
(ownership: sglang multimodal_gen scheduler); no project-side patch is
applied in RC4.1 (patching upstream scheduler behavior is out of scope and
would fork behavior). Mitigation available today: stop the server when idle
(`run_with_server.sh` does exactly this per session) — see
`02_IDLE_SPIN_REPRODUCER.md`.

## 3. Project-level readiness mechanism (new)

`scripts/server_readiness.py` — fact-driven FSM over the EXISTING
server-identity receipts (no SGLang modifications):

- facts: identity verify (PID liveness, starttime, argv sha, uid) ·
  scheduler-worker liveness (descendant scan of the VERIFIED pid for the
  sglang diffusion scheduler signature) · /health · /v1/models ·
  ESTABLISHED connections on the port (BUSY hint) · optional progress-file
  deadline (hang guard)
- states: STARTING/READY/BUSY/DEGRADED/WORKER_DEAD/STOPPING/STOPPED/UNKNOWN
- exit codes: 0 READY/BUSY · 3 WORKER_DEAD · 4 not-ready/UNKNOWN ·
  5 DEGRADED · 6 progress-timeout escalation
- Level-2 canary (`canary` subcommand): OPT-IN real short-budget
  generation (ode_steps=4, semantic_max_tokens=300 — never official
  params), hard client timeout, output verified non-trivial; callers must
  hold the GPU lock and only probe a READY (idle) server.

Integration: `run_with_server.sh` step 5/7 requires READY (or BUSY) before
running the wrapped command — a server whose scheduler died during boot is
never handed a pilot.

## 4. Verification matrix

CPU/mock (`tests/test_server_readiness.py`, 13 tests): READY with live
scheduler · BUSY with connections · **WORKER_DEAD with /health 200 (the
key negative control)** · zombie scheduler = dead · server gone = STOPPED ·
PID reuse = UNKNOWN (fail-closed) · HTTP down + scheduler alive = DEGRADED ·
stale receipt = fail-closed · progress-file deadline escalation · cmdline
fallback scheduler detection · exit-code mapping · canary against a stub
server.

Real W7900 (phase B1/B2 receipts): initial READY (real scheduler pid
recorded) · BUSY during generation · READY after completion · WORKER_DEAD
after scheduler SIGKILL while /health=200 · reboot → READY again ·
verified stop → port free.

## 5. Explicit non-claims

- No fix is claimed for the historical ~1/300 in-request hang (not
  reproduced in RC4 or RC4.1 samples; no statistical claim).
- The idle-spin fix belongs upstream; this repo documents, detects and
  operationally mitigates (idle = stop server) — see
  `02_IDLE_SPIN_REPRODUCER.md` for the authorized-owner upstream draft.
