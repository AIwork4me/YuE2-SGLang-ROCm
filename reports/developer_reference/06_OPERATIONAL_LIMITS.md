# 06_OPERATIONAL_LIMITS.md — RC6 A6.2: runtime boundaries

Verified boundaries of the YuE2-on-ROCm reference (what a developer can and
cannot safely do today). Every item is backed by an implementation or a
receipted incident; unknown/unfixed upstream issues are listed as such.

## Resource model

- **Single-GPU serialization (hard boundary)**: benchmark arms and the
  evaluator run sequentially on one GPU. Concurrent generation + evaluation
  is NOT supported (VRAM contention). The `gpu_lock.py` flock
  (`$YUE2_WORKSPACE/gpu.lock`) is the single owner gate — every GPU step
  acquires it; a second job waits (or fails with exit 3 after
  `--wait-s`).
- **GPU lock contract**: holder pid + starttime + cmdline + host recorded;
  stale holders detected (pid liveness + starttime); graceful stop via
  `gpu_lock.py stop --yes` (SIGINT→SIGTERM to the recorded pid only, never
  pkill/SIGKILL); a server that survives both signals leaves the lock
  BLOCKED and later GPU work refuses until `gpu_lock.py unblock --yes`.
- **VRAM budget**: generation steady state saturates the 48 GiB card
  (~47 GiB); Q3O judge peak 42.41 GiB torch-allocated (34 GPU + 14 CPU MoE
  layers). 24 GiB cards: generation expected, Q3O NOT_TESTED (below the
  measured judge peak).
- **Host memory**: Q3O host VmHWM 49.83 GiB under a 55 GiB cgroup limit —
  keep ≥ 5 GiB headroom; 16 CPU threads quota used by the CPU-resident MoE
  blocks.

## Request boundaries

- **Input limits**: bounded by `scripts/input_budget.py` (style/lyrics
  length budgets enforced fail-closed).
- **Long-song timeout**: per-request timeout default 3600 s in the driver
  (`run_wsb.py --timeout`); P99 wall is 497 s, max 584 s — the timeout is a
  safety net, not the operating point.
- **Scheduler readiness**: HTTP `/health` 200 is NEVER treated as
  generation-ready; `scripts/server_readiness.py` checks the worker/model/
  port state (RC4.1 lesson: HTTP healthy while the scheduler child was
  dead).

## Known upstream behaviours (not fixed here, disclosed)

- **Scheduler idle busy-spin (R1-class)**: after a completed request batch,
  the `sgl_diffusion::scheduler` child has been observed spinning one CPU
  core (~99% CPU, 0% GPU) for hours while HTTP stays healthy. Mitigation:
  lifecycle supervisor drains and stops the server after each session;
  detection: `server_readiness.py`. Still present upstream as observed.
- **Worker death with healthy HTTP**: covered by readiness checks + journal
  fail-closed paths.
- **Telemetry gaps**: `peak_memory_mb` = 0.0 and `yue2_stage_seconds` null
  on ROCm (probe backend absent) — memory truth is rocm-smi; stage truth is
  the server log/journal.
- **Cancellation**: Ctrl-C / SIGTERM reach the single lifecycle supervisor,
  which drains, stops the server, terminates the tree, releases the port and
  the lock (order matters: cleanup BEFORE lock release — RC5 atomicity fix).
  A SIGKILL'd session leaves the lock; the next `wait` detects the stale
  holder via pid+starttime.
- **Checkpoint recovery**: campaign driver writes crash-durable
  `journal.jsonl` (append-only, per-candidate result events) + checkpoint
  archives every 16 candidates and on pause; `rc5_supervise.sh` resumes
  from the journal (verified candidates skipped; partial artifacts
  quarantined, never deleted); RC5.1 closed the SIGTERM tail-checkpoint gap
  (tail checkpoints are now never skipped).
- **OOM diagnosis**: rocm-smi + torch allocator deltas are journaled
  per candidate (`candidate_vram_delta_bytes`, `candidate_gtt_delta_bytes`);
  Q3O OOM was root-caused to packing transients + reference cycles (fix =
  in-place stable top-k patch over stock HF experts; the batched path stays
  experimental).
- **No silent CPU fallback**: GPU work runs under `gpu_identity.py`
  physical binding (framework device → BDF → render node → KFD topology →
  compute probe); identity mismatch fails closed
  (GPU_DEVICE_MISMATCH / GPU_COMPUTE_UNVERIFIED).
- **Official CUDA evaluator dependencies**: PER's official engine (vLLM
  0.14.0) and Q3O's official engine (vLLM + FlashAttention 2.8.3) do not
  exist on ROCm — the disclosed substitutions are the transformers backend
  (frozen arm) and vLLM 0.19.1 (corrected arm) / the ROCm-adapted HF judge
  (Q3O). Cross-engine equivalence: see the RC6 scientific reports.

## Failure → recovery quick table

| Failure | Detection | Recovery |
|---|---|---|
| GPU busy / lock held | `reference status` shows holder | wait, or `reference stop` (graceful), or `gpu_lock.py unblock --yes` after verifying the pid is dead |
| Server dead, HTTP healthy | `server_readiness.py check` | lifecycle restart (run_with_server) |
| Session killed mid-campaign | journal intact | `reference resume --run-dir <run>` |
| OOM during Q3O | judge receipts + peak VRAM fields | rerun the failed receipts (judge resumes by identity); check host memory |
| vLLM platform probe failure | "Device string must not be empty" | already worked around in `rc5_asr_vllm_native.py` |
| llvmlite rc=139 (librosa import) | crash code | numba warm-up before torch (automatic) |
