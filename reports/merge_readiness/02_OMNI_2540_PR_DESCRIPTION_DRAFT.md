# 02 — Proposed PR description for sgl-project/sglang-omni#2540

**Status: DRAFT prepared for author approval — not posted.** We do not modify
author-owned PR descriptions. This draft is a proposed replacement body the
author (yiakwy-xpu-ml-framework-team) may adopt, edit or reject. Everything
attributed to the author is quoted from the current PR body / their repos.
Everything attributed to "W7900D verification" comes from
AIwork4me/YuE2-SGLang-ROCm branch `validation/gfx1100-rocm7141`
(`reports/author_acceptance/`, `reports/final_acceptance/`).

**Integration precondition (must-read).** The AMD ROCm execution path
described below exists only after the author integrates
yiakwy-xpu-ml-framework-team/sglang-omni#1 (ROCm reference path, head
`eca7770f`). At the current PR head `85ae4b73` the submitted source is
CUDA-verified only. This description must not be posted as-is until that
integration happens, or section 4 must be reduced to "planned, see PR #1".
Optionally, long-lyrics support for official WSB prompt 164 is
yiakwy…/sglang-omni#2 (head `4c089d19`).

---

## Proposed body

### Motivation

Add YuE2 (multimodal-art-projection) full-song music generation to
SGLang-Omni: AR (semantic + ABC notation) → NAR vocal/instrumental modeling →
VAE decoding to 48 kHz stereo audio, served through the OpenAI-compatible
`POST /v1/audio/speech` endpoint with nested YuE2 JSON input.

Ported from the original SGLang integration
(sgl-project/sglang#42106, branch `add_yue2`, head `ced0ef7d`) onto the
SGLang-Omni model framework.

*(Author, unchanged in substance from current body: the 2-stage streaming
workflow was initially optimized in YuE2 and VeloxVoice; kernel performance
work continues in VeloxVoice.)*

### YuE2 architecture and features

- **Model**: `m-a-p/YuE2-3B` (MOT) + `m-a-p/YuE2-Vae` / benchmark decoder
  `m-a-p/YuE2-Vae-legacy`.
- **Pipeline**: lyric/style-conditioned AR generation (`cot=full` chain of
  thought, ABC + semantic token streams) → NAR refinement → ODE-based VAE
  decoding (`ode_steps`, `vae_core_frames`, `vae_halo_frames`).
- **Optimizations ported**: DeepSelect fastpath (top-k), fused NAR path,
  FA3 attention module, CUDA-graph reuse decoding, batched synthesis
  scaffolding (see `sglang_omni/models/yue2/`: `fastpath.py`, `nar_fast.py`,
  `fa3.py`, `cuda_graph.py`, `song.py`, `batched.py`).
- **Surface**: OpenAI-compatible speech endpoint (`model: "yue2"`,
  `response_format: "wav"`), streaming variants, examples under
  `examples/run_yue2_generate.py`; 26 new files, ~+6,030 lines, purely
  additive except a 9-line capability-test update.

### NVIDIA CUDA execution path (author-verified)

Author's original statements, preserved verbatim from the current PR body:

- "BS=1, full_song generation 7.0s"
- "MAX Conccurency, 1.81 reqs / sec"
- Supported platform: H800 SuperPod.

The author's single-shot test command and server launch script remain in the
current PR body and are retained unchanged (see "How to reproduce").

### AMD ROCm execution path (W7900D-verified, requires PR #1 integration)

With yiakwy…/sglang-omni#1 integrated, the same served source runs on AMD
ROCm by gating the CUDA-only accelerators and falling back to reference
implementations:

- FA3 attention module and DeepSelect/top-k fastpath dispatch to the
  reference ATen attention and reference sampling on ROCm
  (`is_rocm` platform gates in `fa3.py`, `fastpath.py`, `song.py`,
  `stages.py`; +31/−6 source lines total, plus 207 lines of unit tests).
- No kernel substitution, no sampling-math change: weights, seeds and
  generation settings are identical; only the dispatch differs.

Verified on AMD Radeon Pro W7900D (gfx1100, 48 GB), ROCm 7.14.1, torch
2.12.0+rocm7.14.1, real `sgl-omni serve` + `POST /v1/audio/speech`
(accuracy and serving numbers below).

### Code changes and compatibility strategy

- New self-contained `sglang_omni/models/yue2/` package — no changes to
  other models; one additive edit to `tests/unit_test/models/test_model_capabilities.py`.
- ROCm compatibility (PR #1) is deliberately minimal: capability gates, not
  rewrites. CUDA fast paths are untouched (unit-tested invariants).
- Long-lyrics support (PR #2): YuE2 full-song lyrics exceed the generic
  TTS speech-input cap; sets `max_speech_input_chars=None` for YuE2 only
  (3 lines in `config.py`, moss_tts precedent) + tests. Required to serve
  official WildSongBench prompt 164.

### Accuracy / dataset evidence (AMD W7900D, full dataset)

Full WildSongBench: 192 prompts × 2 candidates, **384/384 verified-complete
candidates, strict audit FULL, zero unresolved structural problems**; every
candidate HTTP 200, WAV 48 kHz stereo, per-candidate WAV sha256 journaled.
Run `omniwsb20261014T1323Z`; frozen protocol (dataset e361b85a, model
revision and manifest hashes recorded in the evidence branch).

| Metric (Omni arm, W7900D) | Value |
|---|---:|
| SongBench Global Avg, full 384 | **6.7301** |
| SongBench Global Avg, selected 192 (official PER best-of-2) | **6.7323** |
| PER, full 384 micro | 0.24819 |
| PER, selected 192 micro | **0.17608** |
| MuLan, selected 192 | ≈ 0.5080 |
| AllMusicCaps, selected 192 | ≈ 0.4059 |
| Q3O | **not tested** |

Cross-arm consistency: the same weights served through the original-SGLang
ROCm path (arm A, `ced0ef7d`) scored SongBench GA 6.731 — every SongBench
dimension within ±0.002 of the Omni arm, MuLan/AMC within 0.002. Deterministic
seeds produced identical audio durations across both arms on all 20 pilot
candidates.

Disclosures (see evidence reports for detail):
- PER was computed with a **ROCm evaluator adaptation** — not the author's
  NVIDIA reference evaluator; exact PER parity with the author's 8.44%
  reference is **not** claimed.
- **ASR truncation/capping**: 128/384 unselected samples hit the ASR cap
  (512 capped repeats; capped samples included, never excluded). This, plus
  per-sample ASR noise, explains PER differences vs other arms; non-PER-coupled
  metrics are numerically indistinguishable across arms.
- 5 truncated-but-valid candidates (semantic budget reached) retained and
  scored; no cherry-picking.
- Cross-platform (AMD vs NVIDIA) accuracy equivalence is **not** claimed.

Upstream corroboration (original SGLang PR): the YuE2 original author
independently validated the same pipeline on NVIDIA at SGLang PR commit
`e0683229` — SongBench GA 6.7146 vs native 6.7360, PER 8.15% vs 8.61%
(their comment on sgl-project/sglang#42106, 2026-10-04).

### BS=1 and concurrency evidence (AMD W7900D; GPU batch size = 1)

| Metric (client concurrency C=1, n=24, 0 errors) | Value |
|---|---:|
| E2E latency P50 / mean | **217.3 s / 218.7 s** |
| Generated audio, mean | 223.0 s |
| Real-time generation speed (audio_s/wall_s per request, mean) | **1.030×** |
| Client E2E RTF (wall_s/audio_s, mean) | 0.975 |
| Throughput | ≈ 0.0046 req/s |
| Peak VRAM | 44.04 GB decimal = 41.02 GiB |

Concurrency sweep C=1/2/4/8 (24 requests each): **0 errors at every C**, but
RPS stays constant at 0.0046 and P50 grows linearly (216.7 → 1736.0 s) —
**GPU-internal execution remains serialized** (`SGLANG_YUE2_BATCH_MAX_SIZE=1`;
batched-synthesis recovery is documented by the author in MIGRATION.md).
Client concurrency is not GPU batch size. This is a measured limitation of
the current port, disclosed as such.

Terminology guardrails observed: E2E RTF (wall/audio, includes queueing at
C≥2) is distinct from GPU compute RTF; real-time speed multiplier is the
reciprocal statement of per-request RTF; SongBench quality is unrelated to
serving throughput.

### CUDA regression expectations

- PR #1 changes are platform-gated (`is_rocm`); on CUDA machines the
  dispatch is byte-for-byte the existing fast path. Unit tests pin these
  invariants (`test_yue2_platform_gates.py`, 12/12 pass locally).
- PR #2 caps change affects YuE2 config only; other TTS models keep the
  generic default (tested in `test_yue2_speech_input_cap.py`).
- **What is still needed**: a focused H800 smoke test on the integrated
  commit (see report 05) — the author's existing NVIDIA evidence covers
  `85ae4b73`/`ced0ef7d`, not the post-integration commit.

### Tested hardware / software matrix

| | NVIDIA (author) | AMD (W7900D verification) |
|---|---|---|
| GPU | H800 SuperPod | Radeon Pro W7900D (gfx1100, 48 GB) |
| Stack | CUDA (author's env) | ROCm 7.14.1, torch 2.12.0+rocm7.14.1 |
| Server | sgl-omni serve | sgl-omni serve (real HTTP) |
| Endpoint | /v1/audio/speech | /v1/audio/speech |
| Evidence | single-shot test + author's WSB campaign on SGLang PR | full WSB 384/384 + BS=1/concurrency sweep (this evidence) |

### Known limitations

1. AMD throughput is serialized at GPU batch 1 (~0.0046 req/s); higher client
   concurrency only deepens the queue.
2. ROCm uses reference ATen attention (validated); FA2/AITER alternatives
   were investigated and remain blocked (`ROCm_FA2_SEQUSEDK_INVESTIGATION.md`).
   No speculative substitution attempted.
3. Q3O metric not tested on any arm.
4. PER evaluator is a ROCm adaptation with disclosed ASR capping; not
   comparable 1:1 with the author's NVIDIA reference PER.
5. YuE2 quantization/kv-cache guards discussed for the SGLang ROCm handoff
   are NOT part of the validated W7900D configuration of `85ae4b73`+PR#1.
6. W7900D vs H800 serving numbers are different workloads — see below.

### H800 numbers vs W7900D numbers — read before comparing

The author's "7.0 s full-song / 1.81 req/s" H800 figures and the W7900D
WildSongBench serving results are **not comparable workloads**: a ~223 s
full-length WSB song at BS=1 on W7900D takes ~217 s E2E; a 7.0 s generation
cannot be the same input (song length, token budgets, endpoint and batch
configuration unknown). No speedup ratio is claimed. Requested from the
author for future comparability: exact H800 GPU count, input size, audio
length distribution, token budgets, endpoint/streaming mode and what the
7.0 s measures (AR-only vs full E2E vs short demo).

### How to reproduce

*(Author's existing server launch script and single-request curl command from
the current PR body are retained verbatim — including
`sglang_omni.cli serve --config configs/yue2.yaml`, `SGLANG_YUE2_VAE_DIR`,
`SGLANG_YUE2_FA3=1` for CUDA — together with the W7900D reproduction pointer:
`AIwork4me/YuE2-SGLang-ROCm`, branch `validation/gfx1100-rocm7141`,
`reports/author_acceptance/OMNI_WILDSOGNBENCH_GFX1100.md` and
`OMNI_BS1_CONCURRENCY_GFX1100.md`, which contain frozen manifests, run
configs, sha256 anchors and raw logs.)*

### Related PRs

- Original SGLang integration: sgl-project/sglang#42106
- ROCm reference-path compatibility: yiakwy-xpu-ml-framework-team/sglang-omni#1
- Long-lyrics input support: yiakwy-xpu-ml-framework-team/sglang-omni#2
- SGLang-side ROCm compatibility: yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork#1

### CI and review status

- All six Omni workflows at head are `action_required` — awaiting maintainer
  workflow approval; **no CI has executed yet** (no lint result exists).
- Required next steps: maintainer approval / CI labels; human review
  (FrankLeeeee requested); author integration of PR #1 (and optionally #2).

---

## Author checklist before posting this description

1. Integrate yiakwy…/sglang-omni#1 (`eca7770f`) into `add_yue2` — then the
   dual-vendor statement in this draft is literally true of the submitted source.
2. Decide on PR #2 (`4c089d19`) — recommended: yes (official WSB prompt 164
   otherwise unservable via the speech endpoint).
3. Verify the H800 focused smoke test on the integrated commit (report 05).
4. Preserve/adjust any statement above the author disagrees with — the
   W7900D numbers are quoted from the evidence repo and should not be altered,
   but their placement is negotiable.
