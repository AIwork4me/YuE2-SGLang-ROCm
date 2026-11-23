# RC4.1 M3 — Lifecycle & GPU-lock closure tests

## 1. The gap being closed

RC4 R1-L1 (self-reported): a resume-pilot driver exited without stopping
its server; RC4 R1-C1: `gpu_lock.py wait -- true` acquired/released the
lock instantly (lock DISCIPLINE weaker than the mission rule). RC4.1
delivers the repo-level lifecycle wrapper that holds ONE lock for the
WHOLE session and always closes the server.

## 2. `scripts/campaign_ops/run_with_server.sh` (new)

```
GPU_IDENTITY_VERIFY → START SERVER → HEALTH POLL (bounded)
→ IDENTITY CAPTURE+VERIFY → READINESS (scheduler-aware)
→ EXECUTE COMMAND → VERIFIED STOP → PORT-FREE CHECK
```

Properties (each regression-tested):

- **one continuous gpu_lock hold** for the entire session (gateway pattern
  from run_armB_campaign.sh; the wrapper is the lock holder from before
  boot until after cleanup)
- **no exec past traps**: the wrapper keeps its own INT/TERM/EXIT traps
  (the exec-discards-traps defect class is documented in-repo); signals
  cascade outer → gateway → inner flow → wrapped command via pid-file
  forwarding
- **verified stop on EVERY exit path** — success, command failure, health
  timeout, readiness failure, signals; stop rc 0 (stopped) or 2 (already
  gone) accepted, 3/4/5/6 escalate to lifecycle failure
- **port-free assertion** on the success path
- a server that cannot be accounted for never hides behind exit 0

## 3. Lock-scope proof (live, this mission)

While phase B1 ran (real server + real generation), a concurrent
`gpu_lock.py status` showed `held: true`, `who: rc41-lifecycle-
20261122T234057Z` (receipt in phase_b1.log); after wrapper exit the lock
showed `held: false` with the release receipt written by gpu_lock.py
itself. RC4's `wait -- true` pattern is retired for all RC4.1 sessions.

## 4. Test inventory

`tests/test_run_with_server.py` (5 scenarios, real wrapper + real
gpu_lock/server_identity/server_readiness, stub server):

1. success path: exit 0, marker written, server stopped, port closed,
   events show listening→signal
2. command rc=2 propagates; server still stopped
3. no-scheduler boot (mode=nosched): readiness WORKER_DEAD → wrapper
   fails loudly, server stopped — HTTP 200 alone is never accepted
4. SIGTERM mid-command: exit 143, server stopped, port closed
5. lock held for the WHOLE session: in-command probe sees held=true with
   the wrapper's who-tag; released after exit

Plus the pre-existing suites re-run green (423 passed / 0 failed /
26 honest manifest skips, CI scope) — including gpu_lock contention,
server_identity reverify, and the 16-scenario armB lifecycle suite.

## 5. GPU session closures (real W7900, this mission)

- phase B1 (run_with_server.sh + real sglang server): verified stop
  rc=0-path, port freed, VRAM back to session baseline (see wrapper log +
  phase receipts)
- phase B2 (scheduler-death scenario): documented recovery ladder
  (graceful stop → operator ladder on OUR OWN verified pid), VRAM release
  recorded, fresh reboot READY, final verified stop, port free
- orphan scan: `ps`/KFD sweep before and after each phase — no project
  server left running at mission end (receipt in 00_LIVE_STATE.md)
