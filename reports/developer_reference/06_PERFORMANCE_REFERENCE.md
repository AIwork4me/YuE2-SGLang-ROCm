# 06_PERFORMANCE_REFERENCE.md — RC6 A6: single consolidated performance reference

All numbers re-derived in RC6 from the frozen RC5.1 raw evidence
(`04_PERFORMANCE_RAW.csv`, 384 rows; lifecycle receipts; run summary) —
nothing copied forward without recomputation.

**Units: bytes use binary GiB (= 2³⁰) unless a decimal figure is explicitly
labelled GB. Wall times in seconds (s).**

## 1. Server lifecycle (cold start, W7900D, stack c67d541a)

| Phase | Measured |
|---|---|
| GPU identity verification (physical binding) | 5.0 s |
| GPU idle gate (VRAM < 2 GiB used) | ~0 s |
| Server launch → HTTP `/health` 200 | 40.1 s |
| Server identity capture + verification | 0.4 s |
| Generation readiness (worker/model/port, beyond HTTP health) | 0.3 s |
| **Cold start total (lock → READY)** | **≈ 46 s** |
| First request extra (weight warm-up) | +50–120 s (RC4 measurement, same class) |
| Drain + verified stop + tree termination + port release | 8.0 s |

Source: `lifecycle/20261124T172716Z-1772902/lifecycle-receipt.json` (final
campaign session).

## 2. Per-candidate generation (n = 384, sequential, single GPU)

| Metric | mean | P50 | P90 | P95 | P99 | max |
|---|---|---|---|---|---|---|
| wall (s) | 284.78 | 275.27 | 393.48 | 434.33 | 496.62 | 583.57 |
| audio (s) | 220.76 | 217.18 | 291.10 | 307.42 | 349.33 | 357.20 |
| AR stage (s) | 164.23 | 157.81 | 227.70 | 255.24 | 297.55 | 336.61 |
| NAR stage (s) | 42.15 | 37.19 | 71.09 | 86.14 | 107.83 | 119.06 |
| VAE stage (s) | 78.37 | 72.50 | 117.22 | 123.65 | 137.93 | 281.88 |

- RTF (wall/audio): mean **1.29** · P50 1.28 · P95 1.54 · max 2.27
- Realtime multiplier (audio/wall): mean **0.79** · P50 0.78 · P95 0.95 ·
  max 1.07 (max > 1 = that candidate rendered faster than realtime)
- Total audio produced: 84,770 s (23.5 h); campaign wall ≈ 30.9 h + gaps
- Sequential throughput (server-occupied): **12.64 candidates/h**
- 5 truncated-but-valid candidates (official protocol keeps them); 0
  failures; 0 retries; 384 attempts.

## 3. Memory (generation)

| Quantity | Value | Source/scope |
|---|---|---|
| Peak device VRAM (card total, rocm-smi sampling) | 29.7 GiB | summary sampler `/sys/class/drm/card1` |
| torch-allocated VRAM (campaign steady state) | ~47 GiB card saturation | server holds weights + KV |
| Max per-candidate VRAM delta | 19,214,274,560 B = 17.9 GiB | journal (one outlier; P95 12.57 GB) |
| Max per-candidate GTT delta | 35,020,800 B = 33.4 MiB | journal |
| Host RSS during generation | not the binding constraint | Q3O below is |

## 4. Evaluation costs (RC5.1 measurements)

| Stage | Wall | Notes |
|---|---|---|
| PER full 384×4 repeats (transformers arm) | ≈ 24 h | GPU ~97% busy |
| PER corrected arm (vLLM 0.19.1, E2) | ~3.5 h | batch 8 songs |
| SongBench / MuLan / AllMusicCaps (192 each) | ≤ 1.5 h each | MuQ/embedding scorers |
| Q3O 192 candidates | 4.65 h | mean 87.1 s/candidate |
| Q3O peak VRAM (torch allocated) | 42.41 GiB | 34 GPU + 14 CPU MoE layers |
| Q3O host VmHWM | 49.83 GiB | under 55 GiB cgroup limit → 5.17 GiB headroom |
| Q3O GPU busy (sampled) | 93.41% mean (generation campaign) | /sys/class/drm/card1 |

## 5. Methodology & scope (what these numbers are NOT)

- Per-candidate wall times are **sequential single-GPU** measurements on one
  rig; they are NOT concurrency/throughput claims and NOT request-latency
  SLOs.
- `candidates_per_hour_occupied` counts only server-occupied time; campaign
  wall includes load/launch gaps between sessions.
- Stage timings (AR/NAR/VAE) come from server-side stage records journaled
  per candidate (the HTTP `yue2_stage_seconds` fields are null on ROCm —
  disclosed telemetry gap; server log + journal are the truth).
- VRAM: "peak device VRAM" = total card usage (all processes); "torch
  allocated" = framework allocator view; per-candidate deltas isolate the
  generation increment. Never mix the three.
- RTF and realtime multiplier are exact reciprocals by definition (reported
  both because both conventions appear in the wild).
- Historical comparators: RC4-era Arm A (native PyTorch) P50 706.4 s —
  different path, different number, never averaged with SGLang numbers.

## 6. Compatibility & boundaries

See `06_COMPATIBILITY_MATRIX.md` (statuses: PHYSICAL_PASS /
PARTIAL_PHYSICAL_PASS / EXPECTED_BUT_UNVERIFIED / NOT_TESTED /
UNSUPPORTED) and `06_OPERATIONAL_LIMITS.md` for the runtime boundary list
(single-GPU serialization, lock, timeouts, OOM diagnosis, resume…).
