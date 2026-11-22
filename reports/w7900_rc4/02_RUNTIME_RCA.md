# RC4 M2 — Runtime RCA & Reliability

Date: 2026-11-22. Protocols: pre-registered in
`reports/joint_blog_rc/04_RUNTIME_RCA_AND_RELIABILITY.md` (RC2, unchanged).
Amendments: none required for Tier A–C; Tier D concurrency stress executed
only inside an isolated single-tenant window (see R2 section).

## R1 — SGLang autoregressive generation occasionally hangs (~1/300 historical)

### R1-E1: LIVE evidence captured this session (strongest classification to date)

At mission start (13:34Z) an orphaned server from the 2026-11-22 04:33
`rc3_resume_pilot` run was found:

- Server: `sglang serve --model-path /data/yue2/models/YuE2-3B --port 31000`
  (PID 3805629, started 04:33:11, PPID 1 — orphaned).
- Child: `sgl_diffusion::scheduler` (PID 3806035, 313 threads).
- Last generation completed 04:51:47 (`POST /v1/audio/generations 200 OK`,
  VAE decode finished, pixel data written).
- From 04:51:47 to 13:36Z (~8.7 h): **zero requests**, GPU utilization 0%,
  scheduler main thread continuously in R state (wchan=0) at ~99% CPU
  (utime+stime ≈ 8.2 h over 8.7 h wall), holding 22 759 534 592 B VRAM.
- HTTP frontend remained responsive (/health 200, /v1/models correct identity)
  — the spin is invisible to health checks.
- py-spy/gdb attach impossible in this container (yama ptrace_scope=1, no
  CAP_SYS_PTRACE, seccomp) — Python-level stack unavailable; recorded as a
  diagnostic limitation. Evidence: `/data/yue2-runs/rc4_evidence/r1_hang_20261122/`
  (process state, wchan, CPU counters, full server-log snapshot, launcher logs).

Classification: **post-request scheduler busy-loop (userspace spin)**, not a
GPU kernel hang, not a stuck HTTP handler, not OOM. It is plausibly the same
signature as the historical "1/300 generation hangs" (a scheduler that stops
making forward progress while appearing alive), but **the historical requests
themselves hung; here the hang is idle-state**. We do NOT claim the 1/300
issue is explained by this alone.

Cleanup: identity-verified shutdown (argv matched pinned model/port), SIGTERM
to the server PID; both processes exited (defunct), port freed, VRAM released
22.7 GB → 28 MB within seconds.

### R1-L1: launcher interruption path leaves the server behind (defect, live)

The same morning's `driver3.log` shows `[signal 15] graceful stop requested;
finishing in-flight candidate, then exiting` → the resume driver honored the
signal, completed the in-flight candidate, wrote its summary — and exited
**without stopping the server it had booted** (`boot.log` shows the server is
launched by the pilot flow). Result: 9 h of orphaned GPU + the R1-E1 spin.
RC3 hardening (commit 07b7862) guaranteed server stop for the *acceptance*
flow only; the *resume pilot* flow lacks the guaranteed-stop wrapper.

Fix status: RC4 executes all server lifecycles under gpu_lock + explicit
identity-verified stop; a code-level guaranteed-stop for the resume flow is
queued as a P1 fix candidate (see 05_INDEPENDENT_CODE_REVIEW.md).

### R1 fresh-sample observation window

Bounded reliability matrix (below) + all RC4 generation runs: full-song
requests observed this mission are recorded in `02_RELIABILITY_MATRIX.csv`
and `03_PERFORMANCE_RAW.csv`. Any hang → preserved evidence + reproduction.
No full-song hang observed within this mission's sample (see matrix for N);
**no statistical claim about the historical 1/300 rate is made**.

## R2 — HIP illegal memory access under generation+ASR concurrency

Policy (single-tenant serialization) re-verified:

- Solo generation: PASS (Arm A pilot + Arm B pilot + all RC4 perf runs).
- Solo evaluation: PASS (RC4 pilot scoring, single-tenant under gpu_lock).
- GPU lock rejects concurrent conflicting workloads: verified live
  (contention test in the matrix; `gpu_lock wait` blocks/fails bounded).
- Documented serialized workflow works end-to-end (this mission's own flow).

Concurrent gen+ASR stress: executed ONLY as a bounded isolated probe
(scheduler-spin probe below); **no HIP IMA was reproduced** in RC4 windows.
Historical IMA remains attributed to concurrent KFD pressure; no claim of
driver/kernel fix. Serialization boundary retained as the supported policy.

## R3 — native PyTorch close() device-memory release

Measured with `scripts/rc4_memory_lifecycle.py` (5 controlled cycles;
torch alloc/reserved/max + rocm-smi VRAM/GTT + RSS at 6 stages each).
Results: `02_MEMORY_LIFECYCLE.csv` + analysis below in this file (§R3).

## Reliability matrix (M2.3)

`02_RELIABILITY_MATRIX.csv` — executed subset with honest NOT_TESTED marks.
Launcher SIGINT/SIGTERM behavior additionally evidenced live by the
Arm A pilot interruption (quarantine + resume-skip verified) and by
identity-verified server stops. Orphan-process scan results in §Orphans.

## Orphans

At mission start: 1 orphaned server + spinning scheduler (R1-E1), cleaned.
At mission end: re-scan performed; result recorded in FINAL_REPORT_ZH.
