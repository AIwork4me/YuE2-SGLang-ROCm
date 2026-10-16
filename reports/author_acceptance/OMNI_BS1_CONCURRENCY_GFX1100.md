# SGLang-Omni YuE2 Serving Performance on Radeon W7900 (gfx1100) — BS=1 Latency and Concurrency

Benchmarks: 2026-10-16 · AMD Radeon Pro W7900D 48GB (gfx1100) · ROCm 7.14.1 · torch
2.12.0+rocm7.14.1 · sgl-omni 0.1.7 (bench/omni-wsb @ c4841f0c = PR#1 head
50c91c08 + comment-only + bench-only artifacts export; serving tree
byte-identical model code; the input-cap worktree was NOT used here — all mix
prompts are under the generic cap). GPU batch fixed at 1
(SGLANG_YUE2_BATCH_MAX_SIZE=1), one server, 127.0.0.1:32100, real
`POST /v1/audio/speech` with the frozen WSB nested JSON (verbatim dataset
style/lyrics; cot=full; cfg 1.0; abc 4096; semantic 9000; ode 32; vae core
1024 / halo 16). Non-streaming endpoint: no TTFA is reported.

## 1. Workload and methodology

- Fixed mix: WSB prompt indices [0, 22, 63, 75, 100, 120, 150, 170] (4 zh /
  4 en by dataset grouping), 3 repetitions, seeds = candidate_ar_seeds[rep%2]
  — 24 requests per stage, identical workload across all C.
- Closed-loop load generator (worker threads take the next item until the
  queue drains); per-request E2E latency measured client-side; audio seconds
  decoded from returned WAV headers; VRAM/GTT from sysfs; GPU utilization
  polled from rocm-smi every 2 s.
- BS=1 stage measured with a separate warm-up request (excluded). The sweep
  ran without additional warm-up (server already warm from BS=1 stage).
- Model loading is NEVER included: server booted + health-checked before each
  stage; the first measured stage additionally discarded a warm-up request.
- 384-sample stage split (AR / NAR+VAE) computed from the frozen WSB run's
  plan.json timing dictionaries (that generation was itself BS=1 serial), not
  re-measured here.

## 2. Cold startup (separate from warm serving)

Launcher → uvicorn serving on 127.0.0.1:32100: **~21–25 s** (local warm-disk
weights reload; torch 2.12+rocm7.14.1; log: server_omni_capfix.log
2026-10-16T00:23:22Z → 00:23:43Z).

## 3. BS=1 latency (client concurrency = 1)

| Metric | Value (n=24, 0 errors) |
|---|---:|
| HTTP 200 success rate | 24/24 = 100% |
| E2E latency P50 / mean | 217.3 s / 218.7 s |
| E2E latency P95 / P99 | 274.9 s / 310.0 s |
| Generated audio mean | 223.0 s |
| Audio seconds per wall second | 1.0197 |
| RTF (audio_s / request wall_s) mean | 1.030 |
| Peak VRAM | 44.04 GB (decimal) |
| GPU utilization (sweep C=1 re-measure) | mean 99.4% / P90 100% |

## 4. Stage separation (BS=1, 384-candidate WSB statistics)

| Stage | mean | median | share |
|---|---:|---:|---:|
| AR total (abc + semantic + transition) | 201.0 s | 194.0 s | 93.7% of E2E |
| AR p95 | 317.7 s | — | — |
| NAR + VAE decode + audio serialization (wall − AR) | 13.4 s | 11.7 s | 6.3% |
| Client-side pre-processing + HTTP + FLAC finalize overhead | ≤ 1.4 s (mean 214.4 s server-side wall vs 218.7 s client E2E) | | |

Source: `benchmarks/stage_split_wsb384.json` (384 plan.json timing dicts).

## 5. Concurrency sweep (GPU batch = 1; client C = 1/2/4/8)

| C | OK / issued | errors | RPS | audio-s/wall-s | P50 s | P95 s | P99 s | RTF mean | peak VRAM GiB | GPU util mean |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 24/24 | 0 | 0.0046 | 1.0180 | 216.7 | 274.9 | 313.8 | 1.029 | 31.4 | 99.4% |
| 2 | 24/24 | 0 | 0.0046 | 1.0230 | 449.5 | 510.7 | 525.9 | 0.533 | 43.1 | 99.7% |
| 4 | 24/24 | 0 | 0.0046 | 1.0232 | 896.0 | 932.1 | 986.0 | 0.304 | 43.2 | 99.8% |
| 8 | 24/24 | 0 | 0.0046 | 1.0234 | 1736.0 | 1804.2 | 1811.0 | 0.204 | 43.2 | 99.8% |

**Delivered concurrency = 1 (GPU-internal execution is serial).** RPS is
constant at 0.0046 (one ~217 s song at a time) across C=1..8; P50 scales
linearly (216.7 → 449.5 → 896.0 → 1736.0 s; C8/C1 = 8.01x)
because additional client requests only deepen queue wait; throughput
(audio-seconds per wall-second ≈ 1.02) is invariant; zero HTTP errors, zero
timeouts, zero OOM at every C; VRAM stable at 43.1–43.2 GB from C≥2 (queued
request state), GPU utilization pinned at ~100%. Client concurrency C=8 is
NOT GPU batch 8: with SGLANG_YUE2_BATCH_MAX_SIZE=1 the yue2_synth stage
admits one synthesis at a time (author's MIGRATION.md documents the pending
batched-synthesis recovery of ~3.2x concurrency). C=16 was not attempted:
admission stability was already proven through C=8 with zero errors, and
latency would only double again with no throughput gain. The model's batching
implementation was NOT modified to influence these results.

## 6. Comparison to the author's H800 reference — questions required first

The author previously stated: "BS=1 full_song 7.0 seconds; max concurrency
1.81 req/s" on H800. A W7900 full WSB song at BS=1 takes ~217 s E2E for ~223 s
of audio — a 7.0 s generation cannot be the same workload (song length,
budgets and endpoint unknown). Before any direct comparison we request:
exact H800 hardware count (GPUs), input style/lyrics size, generated audio
length distribution, abc/semantic budgets, endpoint (streaming?), batch
configuration, and whether 7.0 s is AR-only, full E2E, or a short demo song.
We do not claim W7900/H800 serving equivalence.

## 7. Raw evidence

- `benchmarks/bs1/raw_bs1_C1.jsonl`, `benchmarks/bs1/summary_bs1_C1.json`
- `benchmarks/sweep/raw_sweep_C{1,2,4,8}.jsonl`, `summary_sweep_C*.json`
- `benchmarks/stage_split_wsb384.json`
- Server log `bench/server_omni_capfix.log`; load generator
  `bench/bench_serving_omni.py` (frozen copies mirrored into the evidence
  repository with this report).
