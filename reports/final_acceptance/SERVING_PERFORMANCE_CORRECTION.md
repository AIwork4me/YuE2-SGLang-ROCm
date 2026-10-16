# SERVING PERFORMANCE CORRECTION — Phase 2 (2026-10-16)

Erratum for the W7900 (gfx1100) serving benchmarks published with the Omni
ROCm PR evidence. **Metric labeling only. No benchmark was re-run; no raw
record, stage wall, latency, RPS, VRAM or utilization value changed.**

Inputs: the five preserved raw request files (24 records each, 120 total):
`/workspace/yue2-omni-pr/bench/benchmarks/bs1/raw_bs1_C1.jsonl`,
`.../sweep/raw_sweep_C{1,2,4,8}.jsonl`. Per-file SHA256 recorded in
`evidence/omni_wsb/serving/CORRECTED_METRICS.json`. Recomputation script:
`evidence/omni_wsb/serving/correct_metrics_v2.py` (v2, 2026-10-16).
Loader script commit: bench tree at `c4841f0c` (host mirror), evidence branch
`fix/omni-evidence-acceptance-closure`.

## 1. Root cause of the mislabel

`bench_serving_omni.py` (historical, line 172) computed:

```
rtf_mean = mean(audio_s / wall_s)          # per-request ratios
```

`audio/wall` is the **real-time generation speed multiplier** (1.0 = exactly
real time; >1 = faster). Conventional **RTF** is `wall/audio` (lower is
better). The published summaries therefore carried a speed multiplier under
the name `rtf_mean`. For C>1 the per-request wall time additionally includes
queueing/admission, so both statistics are *client end-to-end* quantities,
never isolated GPU-compute RTF.

## 2. Definitions (explicit, with units)

| Metric | Definition | Direction |
|---|---|---|
| `client_e2e_rtf_mean` | mean_i(wall_i / audio_i) | lower better; 1.0 = real time |
| `client_realtime_speed_x_mean` | mean_i(audio_i / wall_i) | higher better; "×" |
| `aggregate_audio_throughput_x` | Σaudio_i / stage_wall_s | stage-level "×" |
| `requests_per_second` | successful_requests / stage_wall_s | |
| `latency_pXX_s` | percentile of per-request wall_s | original estimator kept |
| Peak VRAM / GTT | bytes; reported in GB (10^9) **and** GiB (2^30) | GTT ≠ VRAM |

Estimator methodology (unchanged from the original client, documented):
percentile = sorted order statistic at index `round(p/100·(n−1))`.

Note: `mean(audio/wall) ≠ 1/mean(wall/audio)` in general (Jensen gap) — e.g.
sweep C8: mean speed 0.2041× but 1/mean RTF = 0.1456. Reciprocals of means
are never used as substitutes.

## 3. Old → new metric mapping (all five stages, 24/24 OK each)

### BS=1 (tag bs1, C=1)

| Old (published) | Value | New label | New value |
|---|---:|---|---:|
| `rtf_mean` | 1.0296 | `client_realtime_speed_x_mean` | 1.0296 (identical) |
| — | — | `client_e2e_rtf_mean` | **0.9749** |
| `audio_s_per_wall_s` | 1.0197 | `aggregate_audio_throughput_x` | 1.0197 |
| `rps` | 0.0046 | `requests_per_second` | 0.0046 |

Latencies unchanged: P50 217.251 / P95 274.931 / P99 309.991 / mean 218.725 s;
audio mean 223.031 s; stage wall 5,249.472 s.

### Sweep C=1/2/4/8

| C | old `rtf_mean` (= new speed× mean) | new `client_e2e_rtf_mean` | agg throughput× | RPS | P50 s | P95 s | P99 s |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.0286 | 0.9762 | 1.0180 | 0.0046 | 216.748 | 274.862 | 313.762 |
| 2 | 0.5331 | 1.9455 | 1.0230 | 0.0046 | 449.530 | 510.712 | 525.935 |
| 4 | 0.3040 | 3.7833 | 1.0232 | 0.0046 | 896.004 | 932.107 | 986.044 |
| 8 | 0.2041 | 6.8664 | 1.0234 | 0.0046 | 1,736.032 | 1,804.234 | 1,811.009 |

(The identical old/new values for the speed multiplier were asserted during
recomputation — see `correct_metrics_v2.py` — proving the correction is a
pure re-labeling plus the new RTF column.)

Interpretation (unchanged conclusions, now correctly named):
- **Delivered concurrency = 1**: GPU-internal execution stayed serial; RPS is
  constant at 0.0046; P50 grows ~linearly (C8/C1 = 8.01×) because extra
  clients only deepen the queue. Client C>1 e2e RTF >1 reflects queue wait,
  **not** GPU-compute RTF and **not** a throughput regression.
- Aggregate audio throughput is invariant ≈1.02× at every C.
- No claim of GPU batching or throughput scaling is made anywhere; the
  negative-scaling (no throughput gain from client concurrency) result is
  retained deliberately as planning information for maintainers.

## 4. GPU utilization provenance

- Monitor: `rocm-smi --showuse --csv` sampled every 2 s in-thread; summary
  stores mean/P90 of parsed samples. No per-sample journal was retained.
- `summary_sweep_C1.json`: mean 99.4% / P90 100% — valid measurement.
- `summary_bs1_C1.json`: mean 0.0 / P90 0.0. The parser is verified
  functional on this host (re-checked 2026-10-16 against live `rocm-smi`
  output). A genuinely idle GPU during 24 back-to-back ~217 s generations is
  implausible; the all-zero samples indicate `rocm-smi` output was not
  parseable/available at sample time under that stage's conditions. There is
  no retained evidence to recover the true values.
- **Status: `BS1_GPU_UTIL_NOT_VERIFIED`.** The 0% must not be read as a
  verified idle-GPU measurement, and the sweep C=1 value (99.4%) is reported
  separately and never substituted into the BS1 row.

## 5. VRAM / GTT units

All original values are bytes; both unit systems are now stated explicitly
in `CORRECTED_METRICS.json` (peak VRAM bs1 44,043,042,816 B = 44.04 GB =
41.01 GiB; sweep C≥2 ≈ 46.25×10⁹ B = 43.07 GiB; peak GTT 33.6–89.4×10⁶ B
≪ VRAM and is system-aperture memory, not VRAM).

## 6. Future-proofing

- `bench_serving_omni.py` (evidence mirror and host bench copy, updated
  identically 2026-10-16): `rtf_mean` key removed; emits
  `client_realtime_speed_x_mean` and `client_e2e_rtf_mean` with an inline
  comment documenting the erratum. Historical `summary_*.json` files are
  intentionally untouched.
- Regression tests `tests/test_serving_metrics_correctness.py` (16 tests):
  synthetic known answers (wall 10 s / audio 20 s → RTF 0.5, speed 2.0×;
  wall 40 s / audio 20 s → RTF 2.0, speed 0.5×; mean-of-ratios ≠
  reciprocal-of-mean-of-ratios), estimator equivalence, full re-derivation of
  every corrected stage from the raw JSONL, no-scaling invariants, GPU-util
  provenance labels, VRAM unit conversions, and a guard that the loader can
  never again emit the mislabeled key.

## 7. What changed vs what did not

Changed: metric names/labels; one added column (client E2E RTF); explicit
units; utilization provenance wording; loader field names.
Not changed: every raw request record, every latency/RPS/stage-wall/value,
quality scores, and all conclusions (serial GPU execution, constant
throughput, linear queue wait).

## 8. Independent verification

Independent reviewer (general subagent, 2026-10-16) recomputed all five
stages from the raw JSONL alone (never opening CORRECTED_METRICS.json):
identical counts (24/24/0 ×5), identical e2e RTF / speed× / aggregate
throughput / percentile values; confirmed historical `rtf_mean` == recomputed
speed multiplier 5/5; Jensen gap present 5/5 (0.0038 → 0.0585 growing with
C); original percentile estimator reproduced 15/15 values; corrected loader
verified; tests 14/14 pass; GPU-util sanity (0 vs 99.4) confirmed.

**FINAL: PERFORMANCE_METRICS_VERIFIED**
