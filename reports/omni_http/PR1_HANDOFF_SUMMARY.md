# PR #1 merge-readiness update — public-safe summary (2026-10-13)

Context: minimal ROCm patch on top of author branch `add_yue2`; integration target
sgl-project/sglang-omni#2540. Prior work: 12/12 platform tests, 37/37 capability tests,
51 CUDA A/B simulated regression cases equivalent, pristine import chain, 3 reviews,
zero P0/P1. This session adds REAL end-to-end evidence on AMD.

## New evidence (gfx1100, W7900 48GB, ROCm 7.14.1, torch 2.12.0+rocm7.14.1)

- Server: `sgl-omni serve` (real Omni entrypoint), endpoint `POST /v1/audio/speech`
- Patch: 50c91c0888312ae784d3c42d9536665aa517dd9d on author base 85ae4b73
- SGLang: pristine upstream checkout — no external SGLang patches required at runtime
- Short-config request (seed 831001, ode 8, vae_core 256): HTTP 200 `audio/wav`,
  48 kHz stereo, 20.479 s, RMS 0.086, SHA256 358ffc66...2feed
- Full-config request (abc 4096 / semantic 9000 / ode 32 / vae_core 1024): HTTP 200,
  47.239 s, RMS 0.147, SHA256 218634d4...26bd; waveforms distinct (no caching)
- Execution on gfx1100 proven: GPU util 0→100% bracketing requests, rocm-smi trace,
  server synth logs (AR looped reference sampling; native ATen varlen attention;
  DeepSelect/fast-sampler/step-graph gated off on ROCm; NAR velocity graph via HIP
  graph API; real VAE decode). No CUDA execution claimed.

## Reviews

Three independent reviews (GPU ops safety, HTTP E2E integrity, upstream merge
readiness): all PASS, zero P0/P1.

## Recommendation

HTTP E2E PASS on gfx1100 supports moving PR #1 from DRAFT to Ready for Review
after owner approval. Remaining action for author: NVIDIA H800 smoke test of the
same /v1/audio/speech contract (CUDA fast paths unchanged by construction and by
the 51-case A/B matrix, but a real NVIDIA run is still outstanding).

Note (separate upstream issue, not this PR): `python-multipart` is an undeclared
runtime dependency of omni's Form/File routes on any platform.

Evidence: private repo AIwork4me/YuE2-SGLang-ROCm, branch evidence/omni-http-gfx1100
(commit dd09618783400c35f976b2f3fe1bdf97ff12f37e); sanitized artifacts available on
request (request/response metadata, audio validation, GPU trace, reviews).
