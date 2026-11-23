# RC4.1 — SGLang diffusion scheduler idle busy-loop: minimal reproducer

Status: REPRODUCED (deterministic) — RC4 (9127 ticks / 90 s = 101% core)
and RC4.1 re-verification (9145 ticks / 90 s = 102% core) on the same
hardware/stack. Prepared for OWNER-AUTHORIZED upstream submission only;
not submitted anywhere by this mission.

## Environment

| Item | Value |
|---|---|
| GPU | AMD Radeon PRO W7900D 48 GB, gfx1100, PCI 0000:03:00.0 |
| Host ROCm | 7.2.1 (kernel interface), userspace wheels rocm7.14.1 |
| torch | 2.12.0+rocm7.14.1 (HIP 7.14.60850) |
| sglang | ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f + repo patchset (patches/*.patch, sha c1e04454854c9abf036a0dcb987302c78606854cda48cc47f54c5ed4853ed7f scope: ROCm compat + evaluator; scheduler untouched) |
| Server | `sglang serve --model-path <YuE2-3B> --port 31000` via scripts/serve_yue2_gfx1100.sh (correctness-first flag matrix) |

## Reproducer (deterministic)

1. Boot the server; wait for /health 200.
2. Complete ONE short generation request cleanly (HTTP 200).
3. Send no further requests. Sample the scheduler child's utime+stime over
   90 s (`/proc/<sched_pid>/stat` fields 14+15).

Measurement (RC4.1, /data/yue2-runs/rc4_1_evidence/20261122T2300Z/
phase_b1.json `idle_scheduler_90s`): ticks delta 9145 over 90 s ≈ 102% of
one core; GPU utilization 0%; VRAM retained (~22 GiB session weights).
Scheduler pid discovered as a descendant of the identity-verified server
pid (scripts/server_readiness.py::find_scheduler_workers).

RC4 additionally observed the same signature persisting 8.7 h on an
orphaned server (r1_hang_20261122/: ~8.2 h accumulated CPU, /health 200
throughout, 22.7 GiB VRAM retained).

## Root cause (code inspection, upstream tree)

`python/sglang/multimodal_gen/runtime/managers/scheduler.py`,
`Scheduler.event_loop()` (line numbers at the pinned commit):

```python
items = self.get_next_batch_to_run()
if not items:
    if self.waiting_queue and self._dynamic_batching_enabled():
        oldest_ts = self.waiting_queue[0][2]
        elapsed_ms = (time.monotonic() - oldest_ts) * 1000.0
        remaining_ms = max(0.0, self._batching_delay_s * 1000.0 - elapsed_ms)
        if remaining_ms > 0 and self.receiver is not None:
            self._poller.poll(timeout=remaining_ms)
        elif remaining_ms > 0:
            time.sleep(remaining_ms / 1000.0)
    continue          # <-- empty queue + no batch: NO sleep, tight spin
```

The backoff path only executes when `waiting_queue` is NON-empty. An idle
server with an empty queue spins the loop body at full core speed forever.

## Expected behavior (suggested upstream direction — NOT a patch)

When no items are runnable and the waiting queue is empty, block on
`self._poller.poll(timeout=<bounded idle backoff>)` (or
`time.sleep(idle_poll_s)`) instead of `continue` — e.g. a small
configurable idle poll interval (10–100 ms). Expected effect: idle CPU
drops from ~100% of one core to ~0%; no latency regression for request
pickup beyond the chosen interval.

## Diagnostic limitations (both RC4 and RC4.1)

Container has yama ptrace_scope=1 and no CAP_SYS_PTRACE → py-spy/py-stack
capture impossible; the code-level RCA above rests on source inspection of
the exact pinned commit plus the deterministic tick signature, not on a
captured Python stack.

## Operational mitigation in THIS repo (until upstream fix)

Servers are session-scoped: `run_with_server.sh` boots, uses, and
identity-verified-stops the server within one GPU-locked session — no
long-lived idle server is left spinning (this is also the RC4 documented
mitigation: "idle = stop").
