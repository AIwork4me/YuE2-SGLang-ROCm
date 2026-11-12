# 04 — Serving Performance (interim, W7900)

**Methodology:** all numbers from live receipts on this rig; cold vs warm
states separated; client concurrency is queueing (one GPU generation at a
time) and is never reported as parallel throughput. RTF = wall time / audio
duration (lower is faster than realtime); speed multiplier = audio seconds
per wall second.

## Generation throughput (campaign driver, official budget)

| Metric | Value | Sample |
|---|---:|---|
| Median full-candidate wall time | 245.8 s | first 9 fresh candidates (armB) |
| Median audio duration | ~200–220 s | same sample (per-candidate in journal) |
| Implied speed multiplier | ~0.85–0.9× | derived |
| Cold start (server → first health OK) | ~75 s | launch receipt |
| Model load + warmup | measured at launch; warmup-mode off | serve log |

## VRAM

| State | VRAM |
|---|---:|
| Server idle (loaded, no request) | ~11 GiB |
| Generating (peak, historical same-stack measurement) | ~41 GiB |
| Concurrent ASR evaluation alongside idle server | feasible (~6 GiB); NOT run alongside generating server (contention policy) |

## Historical reference (same GPU class, prior campaign, unchanged)

BS=1 `/v1/audio/speech` (Omni): P50 217.3 s for mean 223 s audio → 1.030×
real-time multiplier (client RTF 0.975); throughput 0.0046 req/s at
C=1/2/4/8 (queueing). Retained until the fresh post-campaign sweep
supersedes it with same-methodology numbers.

## Pending (post-campaign window)

- Warm/cold request latency split at C=1; queueing demonstration at C=2/4/8
- AR / NAR / VAE stage decomposition (server stage logs already captured)
- Retry/failure accounting (journal fields exist; zero so far after RCA-9 fix)
