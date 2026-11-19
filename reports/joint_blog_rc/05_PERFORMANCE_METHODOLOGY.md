# 05 — Performance methodology (pre-registered before measurement)

Written 2026-11-19 BEFORE any M5 measurement (pre-registration discipline).
Measurements will be executed only in uncontended GPU windows after the Arm B
campaign completes; results land in `05_PERFORMANCE_RESULTS.csv` and
`05_OFFICIAL_METRIC_MATRIX.md` with this file as the frozen method.

## Environment control

- Single tenant (gpu_lock verified held by the harness for the whole window)
- Cold start = fresh process after 60 s idle + dropped caches where safe;
  warm start = second invocation in the same process/session
- All clocks/power states reported (rocm-smi --showclocks --showpower);
  thermal throttling events recorded
- Storage: /data-class local disk; no NFS in the measured path
- Software: the exact RC integrated tree; versions hash-pinned in receipts

## Arm A (native torch-eager) measured quantities

1. Cold start to first token/audio; warm equivalent
2. End-to-end full-song latency distribution (n ≥ 30 representative songs
   from the frozen WSB set; P50/P95/min/max; audio duration recorded)
3. Real-time factor = audio_seconds / wall_seconds (numerator = decoded
   audio duration in the receipt; denominator = generation wall time;
   VAE decode included, model load excluded — stated explicitly per figure)
4. Peak VRAM + GTT (MemoryPoller); host RSS
5. GPU utilization sampling (rocm-smi 1 Hz, reported mean/P95)
6. Failure/recovery overhead: watchdog restart cost measured, not estimated

## Arm B (SGLang serving) measured quantities

1. Server cold start (model load → /health), warm restart
2. Time-to-first-output where meaningful; end-to-end request latency
   distribution (same n ≥ 30 songs as Arm A — same frozen prompts, paired)
3. RTF (same definition), throughput per GPU-hour (songs/hour and
   audio-minutes/hour)
4. Peak VRAM/GTT; KV/pool occupancy from server metrics
5. Client concurrency C=1/2/4/8 where safely supported, each × fixed song
   set; ACTUAL server batch size reported independently of client C
6. Single-request stream stability; connection drop recovery

## Reporting rules

- No cross-vendor speedups unless hardware+workload+protocol+measurement
   conditions are genuinely comparable (i.e., none unless authors share
   their measurement context)
- Every figure carries: n, cold/warm, concurrency, audio-length distribution
- Paired Arm A × Arm B comparisons use the same frozen prompts/seeds
