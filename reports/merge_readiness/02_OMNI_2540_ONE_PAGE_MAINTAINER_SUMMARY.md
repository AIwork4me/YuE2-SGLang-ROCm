# 02b — Omni #2540: one-page maintainer summary

**PR**: sgl-project/sglang-omni#2540 "Add yue2 [Port from SGLang]" · head
`85ae4b73` · mergeable (no conflicts) · all 6 workflows `action_required`
(none executed) · reviewer requested: FrankLeeeee · no human review yet.

## What does YuE2 integration add?

Full-song music generation (YuE2-3B: AR semantic+ABC → NAR → VAE → 48 kHz
stereo WAV) behind the OpenAI-compatible `/v1/audio/speech` endpoint.
Purely additive: 26 new files under `sglang_omni/models/yue2/` (~+6,030
lines) + a 9-line test update. Ported from sgl-project/sglang#42106.

## Does it work on NVIDIA?

Yes — author-verified on H800 SuperPod (single-shot pytest, sample audio in
PR; author's statements: BS=1 full-song 7.0 s, max concurrency 1.81 req/s).
Additionally the YuE2 original author independently validated the same
pipeline at SGLang PR commit `e0683229`: SongBench GA 6.7146 vs native
6.7360 — "broadly aligned" (comment on #42106, 2026-10-04).

## Does it work on AMD?

Yes, with one integration step pending. Verified on Radeon Pro W7900D
(gfx1100, ROCm 7.14.1, torch 2.12.0+rocm7.14.1) via real `sgl-omni serve` +
`/v1/audio/speech`, using the minimal platform-gate patch in
yiakwy…/sglang-omni#1 (+31/−6 lines: FA3/fastpath/song/stages gates →
reference ATen attention on ROCm). **The author has not yet merged PR #1**;
until then the PR head itself is CUDA-verified only.

## What was really tested? (AMD, full dataset)

- WildSongBench **384/384 candidates, strict audit FULL, 0 structural
  problems**; frozen protocol with recorded dataset/model/manifest hashes.
- SongBench Global Avg **6.7301** (full 384) / 6.7323 (selected 192);
  PER 0.24819 full / **0.17608** selected-192 micro; MuLan ≈ 0.5080;
  AllMusicCaps ≈ 0.4059. Within ±0.002 of the independent original-SGLang
  ROCm arm on every SongBench dimension.
- Serving: BS=1 P50 E2E **217.3 s** (mean 218.7 s, audio 223 s, n=24, 0
  errors); real-time speed 1.030×; client E2E RTF 0.975; throughput
  ≈ 0.0046 req/s; sweep C=1/2/4/8 → 0 errors, RPS flat, P50 linear.

## Was accuracy materially degraded?

No degradation observed on AMD vs the same-model reference arm. Caveats kept
visible: PER uses a ROCm-adapted evaluator with disclosed ASR truncation
capping (128/384 unselected capped; included, not excluded) — exact parity
with the author's NVIDIA PER (8.44%) is not claimed. Q3O not tested.

## Which GPU optimizations are currently disabled (AMD)?

FA3 attention → reference ATen; DeepSelect top-k fastpath → reference path;
CUDA-graph reuse and fused NAR fast paths remain CUDA-side. FA2/AITER
alternatives investigated and left blocked (documented). No sampling or
weight changes anywhere.

## Known limitations (stated, not hidden)

GPU-side execution is serialized (batch max 1): ~0.0046 req/s regardless of
client concurrency — higher C only deepens queue wait. Author's 7.0 s H800
figure is a different, unspecified workload; no cross-vendor speedup ratio
is claimed (comparable workload metadata requested from the author).

## What needs to happen before merging?

1. **Author**: integrate PR #1 (ROCm gates) and PR #2 (long-lyrics cap fix,
   needed for official WSB prompt 164) into `add_yue2`.
2. **Author**: focused H800 smoke test on the integrated commit
   (checklist in evidence report 05).
3. **Maintainer**: approve the six `action_required` workflows / add CI
   labels (no YuE2 CI model selector exists today — see report 03).
4. **Maintainer**: human review (FrankLeeeee requested).
5. Lint has never run — run local pre-commit before push (report 04 covers
   the preview integration lint state).

Evidence: `AIwork4me/YuE2-SGLang-ROCm` branch `validation/gfx1100-rocm7141`
(`reports/author_acceptance/`, `reports/final_acceptance/`) — raw logs,
manifests, sha256 anchors, five independent reviews (4 PASS + 1 PASS-with-notes, notes resolved).
