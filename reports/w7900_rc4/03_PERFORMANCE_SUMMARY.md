# RC4 M3 — Performance Summary (W7900D, gfx1100)

> **RC4.1 amendment (2026-11-22):** this file was written mid-run when the
> raw CSV held 786 rows and Arm A fresh n=2 (+6 in flight). The final CSV
> contains **791 measured rows** and Arm A fresh n=7. The tables below carry
> the FINAL numbers; the historical mid-run text is preserved in git history
> (snapshot `21c803d`). P95 values are now computed with the declared
> linear-interpolation method (`scripts/verify_rc4_evidence_consistency.py`),
> which corrected drift in the previously hand-rolled aggregates.

Methodology: frozen pre-registration `reports/joint_blog_rc/05_PERFORMANCE_METHODOLOGY.md`.
Raw data: `03_PERFORMANCE_RAW.csv` (791 measured rows; one row per request;
no invented numbers). Fresh RC4 runs reuse NO campaign audio; campaign rows
are the frozen single-tenant receipts (same stack pins — see drift check).

## Full-song end-to-end wall time (generation only; model load excluded; VAE
decode included; one request at a time)

| Path | Source | n | P50 | P95 | mean | min | max | failures |
|---|---|---|---|---|---|---|---|---|
| Arm B — SGLang serving | campaign (frozen) | 384 | 275.3 s | 429.2 s | 284.5 s | 69.4 | 585.0 | 0 |
| Arm B — SGLang serving | RC4 fresh, warm server | 14 | 248.3 s | 335.6 s | 272.8 s | 227.8 | 366.5 | 0 |
| Arm B — SGLang serving | RC4 fresh, first requests after cold boot | 2 | 305.9 s | 410.7 s | 305.9 s | 189.5 | 422.4 | 0 |
| Arm A — native torch-eager | campaign (frozen) | 384 | 706.4 s | 1028.2 s | 726.2 s | 331.3 | 1198.9 | 0 |
| Arm A — native torch-eager | RC4 fresh, cold process | 7 | 630.4 s | 809.5 s | 658.6 s | 516.1 | 858.6 | 0 |

Drift check (fresh vs campaign, same prompts/seeds/stack): Arm B fresh-warm
P50 248 s vs campaign 275 s (within campaign min–max band, same order);
Arm A fresh n=7 P50 630 s vs campaign 706 s — consistent. **No stack drift.**

## Audio real-time multiplier (primary speed metric)

Definition (per mission): `audio_seconds / generation_wall_seconds` —
how many seconds of audio per second of generation. Conventional RTF (the
reciprocal, wall/audio) is NOT the same number and is labeled separately
where quoted.

| Path | Source | n | mean multiplier | P95 multiplier | (equiv. mean RTF) |
|---|---|---|---|---|---|
| Arm B — SGLang | campaign | 384 | 0.7906 | 0.950 | 1.26 |
| Arm B — SGLang | RC4 fresh warm | 14 | 0.7669 | 0.8991 | 1.30 |
| Arm A — native | campaign | 384 | 0.3089 | 0.361 | 3.23 |
| Arm A — native | RC4 fresh | 7 | 0.2906 | 0.3191 | 3.44 |

Interpretation: on this GPU the SGLang path generates songs roughly at audio
real-time pace (0.77–0.79×); the native torch-eager path is ~3.2× slower
than real-time. Same card, same weights, same official parameters.

## Cold vs warm

- Server cold boot (process start → `/health` 200): **30 s** measured 4×
  (initial + 3 restart cycles; `window_server_state/*/cold_boot.json`).
- First-request-after-boot penalty (Arm B pilot, cold server): +50–120 s vs
  warm P50 (kernel compile/MIOpen tuning on first shapes) — 2 samples, indicative.
- Native pipeline cold model load: ~2–3 min per fresh process
  (`02_MEMORY_LIFECYCLE.csv` `load_s`; 5 cycles measured).

## Client concurrency (M3.4)

Client concurrency C=2 and C=4 with short requests (fresh, this mission):

- C=2: walls [15.7, 38.7] s, total 38.7 s → serialized (second waits for first)
- C=4: walls [23.0, 38.7, 52.2, 69.2] s, total 69.2 s → serialized staircase

**Actual GPU serving concurrency is 1** (server runs `batching_mode=dynamic,
batching_max_size=1`): client concurrency only queues. Client C is NEVER
equated to GPU batch size in any RC4 figure. C=8 not re-run (RC2-era
evidence already showed the same serialization; no new information
expected; recorded as NOT_RE-RUN).

## Throughput

- Arm B: 384 candidates in 113 775 s single-server wall = 1 candidate /
  296 s ≈ **12.2 songs/h** ≈ 45 audio-min/h (campaign receipt).
- Arm A: per-candidate serial ≈ 1 song / 12 min ≈ 5 songs/h (campaign mean).

## Comparisons (same card only)

Absolute: Arm B P50 275 s vs Arm A P50 706 s → SGLang serving is ~2.6×
faster per full song on THIS W7900D with identical weights/parameters.
Configuration differences disclosed: Arm B uses the sglang serving stack
(commit ced0ef7d + patches, HIP graphs session path, ATen flash attention);
Arm A uses the official yue2-infer torch-eager backend (public SDPA) with a
24 GiB memory budget (weights largely host-resident/streamed — see resource
envelope). No cross-vendor comparisons are made.

## Input/output distribution

Campaign audio output mean 220.8–223.7 s per song (both arms); prompt set =
frozen WSB 192 prompts (licensed; not redistributed). Fresh runs report
audio seconds per row in the raw CSV.
