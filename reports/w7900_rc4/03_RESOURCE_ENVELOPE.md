# RC4 M3 — W7900 Resource Envelope (measured)

All figures measured on this rig (single GPU, single tenant). Sources:
run summaries (`generation_summary.json` peak counters), rocm-smi at
runtime, `02_MEMORY_LIFECYCLE.csv`, server boot/state receipts.

## VRAM

| State | Peak VRAM | Notes |
|---|---|---|
| SGLang server idle (loaded, no request) | ~10.3–11.7 GiB | boot + first short request observed |
| SGLang generating (official full-song params) | **47.1 GiB** (pilot receipt) / **51.5 decimal GB (= 47.98 GiB) = 100% of the 48 GiB card** (campaign receipt) | campaign peak equals total VRAM (51,522,830,336 bytes) — the full-campaign envelope SATURATES the card; OOM headroom is zero at official parameters |
| Native torch-eager (24 GiB budget) | GPU-side torch alloc ~0.35 GiB during generate; weights streamed from host (RSS ~12.7 GiB) | budget-bound by design |
| After identity-verified server stop | 28 MiB | full release verified every window |
| After orphaned-server cleanup (R1-E1) | 22.7 GiB → 28 MiB | release on shutdown is immediate once the process actually exits |

## GTT

Campaign Arm B peak: 3.14 GiB · RC4 pilot: ~35 MiB · RC4 window runs:
30–41 MiB (GTT grows with host-mapped buffers under load).

## Host memory (RSS)

- SGLang server main: ~1.0 GiB; scheduler child: ~3.4 GiB idle (313 threads)
- Native pipeline during generation: ~12.7 GiB (weights + streaming);
  after close+GC: ~7.6 GiB baseline retained by interpreter/runtime (bounded,
  non-cumulative — 5-cycle evidence)
- Evaluator (metrics venv) at scoring: additional GiB-scale host memory on
  the same host during solo scoring windows (serialized with generation)

## GPU utilization / clocks / thermals

- Generating: sustained 92–100% GPU use (rocm-smi 1 Hz spot samples during
  pilots/window)
- Idle server (post-request busy-loop state): 0% GPU while the scheduler
  child spins ~1 CPU core (see 02_RUNTIME_RCA R1-E1/idle-sample) — GPU idle
  + CPU burn is the signature to watch for
- Thermals: no throttling events observed in any RC4 window (spot checks)

## Reliable workload boundary (this rig)

1. Full-song SGLang generation: reliable at C=1 (768/768 campaign+RC4
   candidates, 0 generation failures); VRAM envelope saturates at campaign
   scale — do NOT co-schedule anything GPU-side during full-song serving.
2. Concurrency: client-side queuing only (server batch = 1); tail latency
   grows linearly with queue depth (measured C=2/4 staircases).
3. Generation + evaluation concurrency: NOT a supported boundary
   (single-tenant policy; R2 history) — serialize via gpu_lock.
4. Long/degenerate inputs: 40-verse lyrics complete (1 123 s, bounded); a
   ~2.6 KB repeated-tags payload HANGS the request path >60 s (defect
   candidate — see matrix rows `invalid_request` #5/#10); a 2 MB style is
   cleanly rejected (HTTP 500, 1.4 s).
5. Dead scheduler worker: requests hang until client timeout; `/health`
   stays 200 (health ≠ generate-ability); no server-side watchdog; worker
   is never respawned. Recovery = identity-verified stop (SIGINT; SIGTERM
   if shutdown hangs; operator SIGKILL as last resort, evidence preserved).
