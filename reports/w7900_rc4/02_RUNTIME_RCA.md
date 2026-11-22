# RC4 M2 — Runtime RCA & Reliability

Date: 2026-11-22. Protocols: pre-registered in
`reports/joint_blog_rc/04_RUNTIME_RCA_AND_RELIABILITY.md` (RC2, unchanged).
No post-hoc protocol edits; additions below are evidence and tooling.

## R1 — SGLang generation occasionally hangs (~1/300 historical)

### R1-E1 — orphaned server + scheduler busy-loop (session start, live capture)

At mission start (13:34Z) an orphaned server from the 2026-11-22 04:33
`rc3_resume_pilot` run: last request completed 04:51:47 (HTTP 200); from
then to 13:36Z (~8.7 h) the `sgl_diffusion::scheduler` child span at ~99%
of one core (state R, wchan=0; utime+stime ≈ 8.2 h), GPU util 0%, 22.7 GiB
VRAM retained, HTTP `/health` 200 throughout. py-spy attach impossible
(yama=1, no CAP_SYS_PTRACE — diagnostic limitation). Evidence:
`/data/yue2-runs/rc4_evidence/r1_hang_20261122/`. Identity-verified SIGTERM
→ processes gone, VRAM 22.7 GiB → 28 MiB.

### R1-E2 — idle scheduler busy-loop REPRODUCED after a CLEAN run (mini window)

Fresh server (19:15Z boot, identity receipt), ONE short request completed
normally (200), then 90 s idle sample with zero requests in flight:
**9 127 CPU ticks / 90 s = 101% of one core**, GPU util 61%→0%.
`rc4_evidence/mini_window/idle_scheduler_sample.json`.

Conclusion: the post-request scheduler **busy-polls continuously while
idle** on this stack — deterministic, not intermittent. Every "idle" server
burns a full CPU core; this is the same signature class as R1-E1 (which
persisted for hours). The historical *in-request* ~1/300 hang is NOT
reproduced in RC4 samples (62 short + 18 song + 2 long requests + campaign
768 candidates) and **no statistical claim about its rate or a fix is
made**. Root-cause discrimination (scheduler polling loop vs termination
handling) is bounded by the no-ptrace limitation; candidate mechanism: an
idle-loop without backoff in the scheduler event loop. Follow-up: upstream
minimal reproducer (drafted for owner-authorized submission only).

### R1-L1 — launcher gap: resume pilot exits without stopping its server

Live evidence (04:51Z driver3.log): SIGTERM → finish in-flight → summary →
exit, server left running. RC3 hardening covered the *acceptance* flow
only. RC4 executes all server lifecycles with identity-verified stop traps;
an in-repo pilot-with-server wrapper remains follow-up work.

### R1-C1 — my RC4 scripts' lock-scope defect (self-reported)

`gpu_lock.py wait -- true` in my window scripts acquired/released the lock
instantly instead of holding it for the whole server session (the campaign
launcher wraps the ENTIRE flow and holds it). Single-tenancy was still
physically maintained in every window (KFD process list verified before,
during, after; no other GPU workload existed), but the lock DISCIPLINE was
weaker than the mission's rule. Recorded here for honesty; campaign tooling
(`run_armB_campaign.sh`) is the correct pattern.

## Health-endpoint blind spots (new, from fault injection)

1. **Dead scheduler worker is invisible to `/health`**: SIGKILL of the
   scheduler child mid-generation → in-flight request hangs until client
   timeout (curl rc=28 at 900 s), `/health` stays 200, server process
   alive, worker never respawned. (sigkill1/2 receipts; the second kill
   re-targeted the same dead PID — confirming no respawn.)
2. **Half-shutdown state**: SIGINT stop → uvicorn closes the listening
   socket but the process hangs in "Waiting for background tasks" (the
   hung request coroutine); `server_identity.py stop` then correctly
   REFUSES (rc=3, socket owners ambiguous). Recovery ladder applied and
   evidenced: SIGTERM (no exit in 20 s) → operator SIGKILL → immediate VRAM
   release. The identity tool never SIGKILLs by design (safe default).

## Invalid/degenerate input behavior (matrix battery)

50/50 short valid requests OK (p50 20.2 s); 8/10 invalid payloads cleanly
rejected (HTTP 422 in 0 s); **~2.6 KB repeated-tags payload hangs the
request path >60 s** (2/2 occurrences — defect candidate; a 2 MB style is
cleanly rejected with HTTP 500 in 1.4 s); 40-verse long-lyrics request
completes bounded (1 123 s, 200 OK).

## R2 — HIP IMA under generation+ASR concurrency

Policy retained and re-verified: solo generation PASS (all RC4 windows);
solo evaluation PASS (pilot scoring windows); lock contention fail-closed
(live); serialized workflow executed end-to-end this mission. Concurrent
gen+ASR stress NOT executed (single-production-GPU discipline). No HIP IMA
reproduced in any RC4 window. No driver/kernel-fix claims.

## R3 — native PyTorch close() device-memory release

5 controlled cycles (`02_MEMORY_LIFECYCLE.csv`): close() releases torch
allocations 346→80 MiB; GC releases ~1.4 GiB RSS; after empty_cache the
baseline (80 MiB alloc / 7.6 GiB RSS) is stable and **non-cumulative**
across cycles. Classification: bounded caching-allocator + runtime residual,
NOT a leak. The RC1 "memory cleanup unresolved" item closes as narrowed.
(memory_allocated vs memory_reserved kept distinct throughout;
rocm-smi csv parsing unavailable in-container — vram/gtt columns are null
in the CSV; device-side truth captured by run-summary peak counters.)

## Reliability matrix (M2.3) — executed inventory

Executed: 50 short valid, 10 invalid, 5 cancel-equivalent live events
(3 driver SIGTERM interruptions + 2 scripted cancel tests), 16 complete
songs (perf run) + 4 pilot songs + 1 long-lyrics + 1 oversized, 4 server
boots (initial + 3 restart cycles) + 1 post-SIGKILL reboot, 2 child-worker
SIGKILL tests, 1 idle-scheduler probe, lock contention, orphan scan (start
and end). NOT executed as scripted: 2nd independent SIGKILL (re-killed the
same dead worker — counts as respawn-check evidence instead), C=8 re-run
(RC2 evidence covers), destructive disk-guard trigger (by-inspection only).
Rows: `02_RELIABILITY_MATRIX.csv` + window logs + probe JSONs.

## Lifecycle guarantees — status

request-id stability PASS · server lifecycle PASS (with the two documented
blind spots) · timeout boundedness PASS (every request/client/stop bounded)
· retry bounds PASS (driver bounded retries; matrix CLIENT_ERRs bounded) ·
cancellation PASS (graceful stop, quarantine, resume — live×3) · resumption
PASS · duplicate-complete rejection PASS (auditor) · partial-artifact
quarantine PASS (live + auditor fixed to recognize it) · output immutability
PASS (write-once; frozen-evidence hash recheck at mission end) · corrupt
artifact rejection PASS (identity recompute) · failure codes PASS (2/3/4/5
semantics exercised) · no silent fallback PASS (asserts + guards) · lock
release PASS · port cleanup PASS · GPU release PASS.
