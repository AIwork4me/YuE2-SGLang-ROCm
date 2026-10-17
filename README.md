# YuE2 on AMD ROCm
## Verified SGLang & SGLang-Omni Reproduction

Independent, evidence-first reproduction of YuE2 (`m-a-p/YuE2-3B`) song generation on
AMD GPUs under Linux-native ROCm, using the SGLang and SGLang-Omni `yue2` branches from
upstream PR [sgl-project/sglang#42106](https://github.com/sgl-project/sglang/pull/42106).

**Yes — YuE2 runs end-to-end on AMD ROCm today**, on two verified consumer platforms:

- **AMD Radeon 8060S (gfx1151, Ryzen AI MAX+ PRO 395)** — SGLang path, full official
  WildSongBench: 384/384 candidates, strict audit `FULL`, official scoring complete.
- **AMD Radeon PRO W7900 48 GB (gfx1100)** — both the original SGLang path and the
  SGLang-Omni path: two independent full 384/384 WildSongBench runs with matching
  quality, plus BS=1/concurrency serving benchmarks.

**Nothing is merged upstream yet.** All five related PRs were still open at the
2026-10-17 verification (see [Upstream merge status](#10-upstream-merge-status)).
Our code contributions live as PRs against the author's forks — see the
[contribution tracker](#5-existing-upstream-contributions).
All evidence is in this repository: start from the
[Evidence index](#7-evidence-and-verification-index) or
[`docs/EVIDENCE_INDEX.md`](docs/EVIDENCE_INDEX.md).

> Status snapshot verified 2026-10-17 against `main` @ `038acf2b`,
> `validation/gfx1100-rocm7141` @ `137ce40d`, and the live GitHub API.

---

## Contents

1. [Executive summary](#1-executive-summary)
2. [Verification status](#2-verification-status)
3. [Tested AMD GPU / platform matrix](#3-tested-amd-gpu--platform-matrix)
4. [Benchmark highlights](#4-benchmark-highlights)
5. [Existing upstream contributions](#5-existing-upstream-contributions)
6. [Reproduce on AMD ROCm](#6-reproduce-on-amd-rocm)
7. [Evidence and verification index](#7-evidence-and-verification-index)
8. [Known limitations](#8-known-limitations)
9. [Security and provenance](#9-security-and-provenance)
10. [Upstream merge status](#10-upstream-merge-status)
11. [Licensing and acknowledgments](#11-licensing-and-acknowledgments)

## 1. Executive summary

YuE2 has been independently validated end-to-end on AMD ROCm using the SGLang and
SGLang-Omni `yue2` development branches. Three full official WildSongBench campaigns
(192 prompts × 2 candidates = 384 generations each) were completed on W7900 (gfx1100,
twice: original SGLang and SGLang-Omni stacks) and on Radeon 8060S (gfx1151), each
passing a strict 384/384 artifact audit with verdict `FULL` and receiving official
frozen-evaluator scoring (PER, SongBench, MuQ-MuLan, AllMusicCaps).

The two W7900 stacks — the same YuE2 weights served by two independent integrations —
agree on every SongBench dimension to within ±0.002 on the unselected-384 arm (the
frozen comparison arm; selected-arm Global Avg differs by 0.004), which is the central
acceptance evidence that the Omni ROCm reference path reproduces the original SGLang
ROCm path's measured quality. Reproducible serving evidence (BS=1 latency, client
concurrency 1/2/4/8) is published for W7900.

What is **not** claimed: no official NVIDIA-vs-AMD accuracy parity (evaluator
revisions and ASR capping conditions differ), no H800 rerun on the final combined
patch commit, and no upstream merge — official upstream support remains pending.

## 2. Verification status

| Area | Status | Where verified |
|---|---|---|
| gfx1151 full 384-candidate generation | **VERIFIED** — strict audit `FULL` (384/384, 13 truncated-but-valid included) | [`evidence/final_generation_audit.json`](evidence/final_generation_audit.json) |
| gfx1151 official WSB scoring (PER, SongBench, MuLan, AllMusicCaps) | **VERIFIED** — complete, frozen evaluator, PER-based best-of-2 selection | [`evidence/official_scores.json`](evidence/official_scores.json), [`evidence/official_scores_additional.json`](evidence/official_scores_additional.json) |
| gfx1100 (SGLang) full 384-candidate run + scoring | **VERIFIED** — strict audit `FULL`, official scoring | [`evidence/gfx1100/scoring_snapshot.json`](evidence/gfx1100/scoring_snapshot.json), [`reports/upstream/YUE2_FINAL_MERGE_AND_WSB_HANDOFF.md`](reports/upstream/YUE2_FINAL_MERGE_AND_WSB_HANDOFF.md) |
| gfx1100 (SGLang-Omni) full 384-candidate run + scoring | **VERIFIED** — strict audit `FULL`, official scoring, author-acceptance report | [`validation/gfx1100-rocm7141` @ `137ce40d`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/author_acceptance/OMNI_WILDSOGNBENCH_GFX1100.md) |
| gfx1100 serving performance (BS=1, C=1/2/4/8) | **VERIFIED** — with published RTF-labeling erratum | [`OMNI_BS1_CONCURRENCY_GFX1100.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/author_acceptance/OMNI_BS1_CONCURRENCY_GFX1100.md) |
| Evidence integrity (pilot/full artifact mix-up closure) | **VERIFIED** — 2026-10-16 reorganization, all sha256 anchors matched | [`EVIDENCE_INTEGRITY_CLOSURE.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/final_acceptance/EVIDENCE_INTEGRITY_CLOSURE.md) |
| Q3O metric | **NOT TESTED** — flash-attn 2.8.3 is CUDA-only; 80 GB judge requirement | [`reports/PHASE7_METRICS.md`](reports/PHASE7_METRICS.md) §3 |
| NVIDIA H800 regression on final combined patch | **NOT TESTED by us** — hardware not available; handoff instructions prepared | [`H800_HANDOFF_CORRECTED.md`](reports/merge_closure/H800_HANDOFF_CORRECTED.md) |
| Official upstream merge (SGLang / SGLang-Omni) | **PENDING UPSTREAM** — all PRs open | [§10](#10-upstream-merge-status) |

The historical per-phase engineering reports (`reports/PHASE0…PHASE7`,
`reviews/PHASE0…PHASE5`) are retained as-is; their in-report "IN PROGRESS" headers
predate completion and are superseded by the machine-readable final artifacts above.

## 3. Tested AMD GPU / platform matrix

| Hardware | GPU arch | Framework | End-to-end | Dataset score (selected 192) | Source evidence |
|---|---|---|---|---|---|
| AMD Radeon 8060S 32 GB (Strix Halo iGPU, Ryzen AI MAX+ PRO 395) | gfx1151 | SGLang (PR #42106 + ROCm patches 0001–0005) | **VERIFIED** (384/384, audit `FULL`) | SongBench 6.683 · PER 17.22% · MuLan 0.505 · AMC 0.412 | `main`: [`official_scores.json`](evidence/official_scores.json), [`environment.json`](evidence/environment.json) |
| AMD Radeon PRO W7900 48 GB | gfx1100 | SGLang (PR #42106 @ `ced0ef7d`) | **VERIFIED** (384/384, audit `FULL`) | SongBench 6.736 · PER 17.01% · MuLan 0.510 · AMC 0.405 | `main`: [`evidence/gfx1100/scoring_snapshot.json`](evidence/gfx1100/scoring_snapshot.json) |
| AMD Radeon PRO W7900/W7900D 48 GB | gfx1100 | SGLang-Omni (author `add_yue2` + our PRs #1/#2 + style commits) | **VERIFIED** (384/384, audit `FULL`) | SongBench 6.732 · PER 17.61% · MuLan 0.508 · AMC 0.406 | [`validation/gfx1100-rocm7141` @ `137ce40d`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/evidence/omni_wsb/scores_summary.json) |
| NVIDIA H800 (upstream reference) | — | SGLang (author's run) | not run by us | author-published values only (different evaluator revisions) | [sgl-project/sglang#42106](https://github.com/sgl-project/sglang/pull/42106) |

Notes: rows are independent campaigns — metrics are **not** merged or interpolated
across hardware, framework, or arms. "Selected 192" is the official PER-based
best-of-2 selection arm; unselected-384 values are in the benchmark tables below.
Software pins: gfx1100 — ROCm 7.14.1, `torch 2.12.0+rocm7.14.1`, WSB dataset
`m-a-p/WildSongBench@e361b85a`, model `m-a-p/YuE2-3B@1a96eca6`, VAE
`m-a-p/YuE2-Vae-legacy@b54118f0`. gfx1151 — host ROCm 7.2.1 userspace with the same
`2.12.0+rocm7.14.1` torch wheels (details in [`evidence/environment.json`](evidence/environment.json)).

## 4. Benchmark highlights

All values below were re-read from the frozen evidence files at the pinned commits —
see [`docs/EVIDENCE_INDEX.md`](docs/EVIDENCE_INDEX.md) for the exact provenance of
every number.

### 4.1 WildSongBench official scoring (frozen evaluator, PER best-of-2 selection)

| Metric | gfx1151 (8060S, SGLang) | gfx1100 (W7900, SGLang) | gfx1100 (W7900, SGLang-Omni) |
|---|---:|---:|---:|
| Candidates generated (strict audit) | 384/384 `FULL` | 384/384 `FULL` | 384/384 `FULL` |
| SongBench Global Avg — unselected 384 | 6.718 | 6.731 | 6.730 |
| SongBench Global Avg — selected 192 | **6.683** | **6.736** | **6.732** |
| SongBench Musicality — unselected 384 | 5.891 | 5.919 | 5.917 |
| PER micro — selected 192 ↓ | 17.22% | 17.01% | 17.61% |
| PER micro — unselected 384 ↓ | 25.34% | 22.75% | 24.82% |
| MuLan — selected 192 ↑ | 0.505 | 0.510 | 0.508 |
| AllMusicCaps — selected 192 ↑ | 0.412 | 0.405 | 0.406 |
| Q3O | NOT RUN | NOT RUN | NOT RUN |

Evaluator caveats (apply to all rows, disclosed in the source reports): the PER
evaluator ran under a ROCm torch substitution (patch 0006/0007, env-gated) with the
transformers-backend ASR (vLLM is CUDA-only); ASR truncation/capping affected
88/384 (gfx1151), 120/384 (gfx1100 SGLang) and 128/384 (gfx1100 Omni) unselected
samples — capped samples are **included** with postprocessed text per the official
policy, never excluded. The author's published NVIDIA H800 numbers were produced
under different evaluator revisions and hardware; **no exact cross-vendor accuracy
equivalence is claimed**. The two W7900 rows (same GPU, two integration stacks) are
the like-for-like comparison and agree within ±0.002 on every SongBench dimension on
the unselected-384 arm (selected-arm GA differs by 0.004).

Sources: [`evidence/official_scores.json`](evidence/official_scores.json) +
[`evidence/official_scores_additional.json`](evidence/official_scores_additional.json)
(gfx1151); [`evidence/gfx1100/scoring_snapshot.json`](evidence/gfx1100/scoring_snapshot.json)
(gfx1100 SGLang); [`scores_summary.json` @ `137ce40d`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/evidence/omni_wsb/scores_summary.json)
+ [`OMNI_WILDSOGNBENCH_GFX1100.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/author_acceptance/OMNI_WILDSOGNBENCH_GFX1100.md) (gfx1100 Omni).

### 4.2 Serving performance (W7900, SGLang-Omni, real `/v1/audio/speech`)

- GPU batch fixed at **BS=1** (`SGLANG_YUE2_BATCH_MAX_SIZE=1`), 24-request fixed WSB
  mix, 0 errors at every stage. **P50 E2E latency 217.3 s** (mean 218.7 s) for a mean
  **223 s of generated audio** — i.e. a real-time speed multiplier of **1.030×**
  (conventional client RTF 0.975). Peak VRAM 41 GiB.
- Client concurrency **C = 1/2/4/8** tested: throughput is constant at
  **0.0046 requests/s** and audio-seconds-per-wall-second ≈ 1.02 at every C; P50
  scales ~linearly (216.7 → 449.5 → 896.0 → 1736.0 s) because **delivered GPU
  concurrency is 1** — client concurrency is queueing, **not** GPU batching. No GPU
  batching scalability is claimed or demonstrated; batched synthesis remains a
  follow-up optimization (see limitations).
- A metric-labeling **erratum** was published (2026-10-16): historical "RTF mean"
  columns were actually the real-time speed multiplier (audio_s/wall_s). Values are
  unchanged; labels corrected in
  [`SERVING_PERFORMANCE_CORRECTION.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/final_acceptance/SERVING_PERFORMANCE_CORRECTION.md)
  and recomputed in
  [`CORRECTED_METRICS.json`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/evidence/omni_wsb/serving/CORRECTED_METRICS.json).
  Audio workload duration matters: these numbers are full-song WSB requests (~223 s
  audio), not short demos. No W7900-vs-H800 speedup ratio is claimed (the published
  H800 "7 s full-song" figure cannot be the same workload without clarification —
  open questions are listed in the serving report).

Source: [`OMNI_BS1_CONCURRENCY_GFX1100.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/author_acceptance/OMNI_BS1_CONCURRENCY_GFX1100.md).

## 5. Existing upstream contributions

Code contributions from this work (all against the author's forks; live states
verified 2026-10-17 — **none merged yet**):

| Contribution | Link | State (2026-10-17) |
|---|---|---|
| Omni ROCm reference path (no CUDA regression) | [yiakwy-xpu-ml-framework-team/sglang-omni#1](https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1) | OPEN, reviewable, head `eca7770f` |
| Omni long-lyrics fix (full-song lyrics in speech requests) | [yiakwy-xpu-ml-framework-team/sglang-omni#2](https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/2) | OPEN, head `4c089d19` |
| Original SGLang ROCm fallback PR | [yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork#1](https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork/pull/1) | OPEN, head `def437fb` |
| Prepared Omni style commit (mechanical lint fixes) | [`ae11c6ad`](https://github.com/AIwork4me/sglang-omni/commit/ae11c6ad246023494a4f55f89e852384e019f5b4) | pushable/cherry-pickable |
| Prepared Omni naming-policy commit (58 symbol renames, bit-identical smoke) | [`b91b9544`](https://github.com/AIwork4me/sglang-omni/commit/b91b95440cf3ce9b6d83f6593d85c91aadffbfd2) | pushable/cherry-pickable |
| SGLang pre-commit lint fix for PR #42106 files | [`1a9f2d92`](https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork/commit/1a9f2d92a201b21242ca6c1bbe8a070189b0a913) | on author's benchmark fork |

Related author-owned carriers (not ours to modify):

| PR | Link | State (2026-10-17) |
|---|---|---|
| Author's Omni carrier "Add yue2" | [sgl-project/sglang-omni#2540](https://github.com/sgl-project/sglang-omni/pull/2540) | OPEN, review required |
| Original SGLang "Add yue2" | [sgl-project/sglang#42106](https://github.com/sgl-project/sglang/pull/42106) | OPEN, conflicts with main (RCA + resolution map published) |

## 6. Reproduce on AMD ROCm

Short version — full details in [`docs/QUICKSTART_W7900.md`](docs/QUICKSTART_W7900.md)
(gfx1100), [`docs/ROCM_INSTALLATION.md`](docs/ROCM_INSTALLATION.md) and
[`docs/BENCHMARK_REPRODUCTION.md`](docs/BENCHMARK_REPRODUCTION.md); gfx1151 setup in
[`scripts/setup_gfx1151.sh`](scripts/setup_gfx1151.sh).

```bash
# 0) environment diagnostic (PASS/WARN per subsystem)
python3 scripts/check_environment.py

# 1) gfx1100: exact ROCm 7.14.1 wheel environment (Ubuntu 24.04, python3.12)
bash scripts/setup_gfx1100_rocm7141.sh

# 2) serve YuE2 on ROCm (SGLang PR #42106 tree + patches 0001-0005)
bash scripts/serve_yue2_gfx1100.sh        # or serve_yue2_rocm.sh on gfx1151 hosts

# 3) run the official WildSongBench protocol (192x2, cot=full, frozen seeds)
python3 scripts/run_wsb_full.py --runs runs/wsb_full

# 4) official scoring (gated on strict 384/384 audit FULL; needs the YuE2
#    workspace root, see the script header)
WS=/path/to/YuE2 bash scripts/run_official_eval.sh runs/wsb_full
```

Pins that matter: `torch 2.12.0+rocm7.14.1` (AMD wheels), model `m-a-p/YuE2-3B`,
VAE `m-a-p/YuE2-Vae-legacy`, dataset `m-a-p/WildSongBench` (revisions + sha256 in
[`evidence/protocol_lock.json`](evidence/protocol_lock.json) and
[`evidence/model_manifest.json`](evidence/model_manifest.json)). Patches
0001–0005 are ROCm compatibility guards only — no model-math changes; the SGLang-Omni
path uses the author's `add_yue2` branch plus our PRs above (development branches,
**not** released upstream installations). On hosts where huggingface.co is
unreachable, the scripts pin `HF_ENDPOINT=https://hf-mirror.com` with full-SHA256
verification of every download.

## 7. Evidence and verification index

Everything is linked with provenance in [`docs/EVIDENCE_INDEX.md`](docs/EVIDENCE_INDEX.md).
Quick pointers:

- **W7900 (gfx1100) SGLang-Omni full WildSongBench report** —
  [`OMNI_WILDSOGNBENCH_GFX1100.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/author_acceptance/OMNI_WILDSOGNBENCH_GFX1100.md)
  (branch `validation/gfx1100-rocm7141`, pinned `137ce40d`)
- **W7900 corrected serving benchmark** —
  [`SERVING_PERFORMANCE_CORRECTION.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/final_acceptance/SERVING_PERFORMANCE_CORRECTION.md)
  and [`CORRECTED_METRICS.json`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/evidence/omni_wsb/serving/CORRECTED_METRICS.json)
- **W7900 evidence integrity audit** —
  [`EVIDENCE_INTEGRITY_CLOSURE.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/final_acceptance/EVIDENCE_INTEGRITY_CLOSURE.md)
- **gfx1151 final generation audit + official scores** —
  [`evidence/final_generation_audit.json`](evidence/final_generation_audit.json),
  [`evidence/official_scores.json`](evidence/official_scores.json),
  [`reports/PHASE6_GENERATION.md`](reports/PHASE6_GENERATION.md),
  [`reports/PHASE7_METRICS.md`](reports/PHASE7_METRICS.md)
- **ROCm compatibility matrices** — [`docs/COMPATIBILITY_MATRIX.md`](docs/COMPATIBILITY_MATRIX.md),
  [`evidence/compatibility_tests.json`](evidence/compatibility_tests.json)
- **Final author merge handoff** —
  [`10_FINAL_MERGE_HANDOFF.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/40bd59f94079345917b526a3e2ee49c8a9f1f867/reports/final_merge_closure/10_FINAL_MERGE_HANDOFF.md)
  (branch `handoff/yue2-upstream-merge-readiness`, pinned `40bd59f9`)
- **Model & dataset references** — [m-a-p/YuE2-3B](https://huggingface.co/m-a-p/YuE2-3B),
  [m-a-p/YuE2-Vae-legacy](https://huggingface.co/m-a-p/YuE2-Vae-legacy),
  [m-a-p/WildSongBench](https://huggingface.co/datasets/m-a-p/WildSongBench),
  [YuE2 WSB benchmark evaluator](https://huggingface.co/datasets/m-a-p/WildSongBench)
  (frozen bundle hashes in [`evidence/protocol_lock.json`](evidence/protocol_lock.json))
- **Independent review verdicts** — [`reviews/`](reviews) (per-phase),
  [`FINAL_INDEPENDENT_REVIEWS.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/final_acceptance/FINAL_INDEPENDENT_REVIEWS.md)

## 8. Known limitations

1. **Official upstream support is not merged.** All five PRs (§5) remain open;
   nothing here is an official SGLang/SGLang-Omni release feature.
2. **NVIDIA H800 not rerun on the final combined patch commit** — no H800 hardware;
   rehearsed, SHA-pinned handoff instructions are prepared for the author.
3. **ROCm reference path, not CUDA-kernel equivalence**: DeepSelect topk, fused
   sgl_kernel decode, and batched-AR are CUDA-only; on ROCm they fall back to
   reference paths behind capability gates (correctness validated; speed cost
   quantified). See [`docs/COMPATIBILITY_MATRIX.md`](docs/COMPATIBILITY_MATRIX.md).
4. **Client concurrency ≠ GPU batching**: with BS=1 the GPU executes one synthesis
   at a time; C=2/4/8 only deepens the queue (§4.2). Batched-synthesis recovery
   (~3.2× per the author's MIGRATION.md) is a pending optimization.
5. **WSB evaluator limitations**: Q3O not executed (flash-attn 2.8.3 CUDA-only +
   80 GB judge requirement); PER ran under ROCm torch substitution and
   transformers-backend ASR; ASR capping affects a disclosed fraction of samples
   (§4.1) — capped samples included, never excluded.
6. **Cross-vendor caution**: no exact NVIDIA-vs-AMD accuracy claims; author reference
   values were produced under different evaluator revisions and hardware.
7. **Single GPU, single run per arm** (frozen two candidates per prompt); no
   multi-seed campaign beyond the official protocol.
8. **gfx1151 uses host ROCm 7.2.1 userspace with rocm7.14.1 torch wheels** — see
   [`evidence/environment.json`](evidence/environment.json) for the exact stack.

More in [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).

## 9. Security and provenance

- A **full-history security audit** of this repository was completed 2026-10-17
  (all refs, 93 commits, all 352 history blobs; two independent scanners plus a
  custom category/entropy sweep; Actions logs sampled). **No credentials or true
  secrets were found.** Methodology, scope and limitations:
  [`docs/PUBLIC_SECURITY_REVIEW.md`](docs/PUBLIC_SECURITY_REVIEW.md).
- **Provenance**: benchmark evidence files contain WildSongBench prompt text
  (song lyrics) and ASR transcriptions of model-generated audio, reproduced for
  scientific reproducibility. The WildSongBench dataset card currently declares
  **no license**; third-party rights in that content are reserved by its authors
  and no redistribution license is claimed beyond referencing it here.
- Environment receipts intentionally record internal host details (paths, GPU
  device names) for reproducibility; no credentials appear in them (the one
  `gh auth status` capture is token-masked by the tool itself).

## 10. Upstream merge status

Verified live 2026-10-17 via the GitHub API:

- [sgl-project/sglang#42106](https://github.com/sgl-project/sglang/pull/42106) —
  **OPEN**, conflicts with main. Our contribution: lint fix `1a9f2d92`, conflict RCA
  and minimal capability-keyed guard map
  ([`SGLANG_42106_HANDOFF.md`](reports/merge_closure/SGLANG_42106_HANDOFF.md)).
- [sgl-project/sglang-omni#2540](https://github.com/sgl-project/sglang-omni/pull/2540) —
  **OPEN**, review required. YuE2 ROCm support rides our
  [sglang-omni#1](https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1) →
  author integration → #2540.
- Author Omni PRs #1/#2 (our contributions) — **OPEN**, awaiting author review;
  prepared style commits `ae11c6ad` + `b91b9544` clear the last YuE2 lint blockers
  (verified: pre-commit green repo-wide, 76/76 unit tests, bit-identical W7900 smoke).
- **Do not read this repository as claiming official NVIDIA + AMD support** —
  official support begins when the upstream PRs merge in `sgl-project/*` history.

## 11. Licensing and acknowledgments

- Code and documentation in this repository: **MIT** ([`LICENSE`](LICENSE)).
- Evidence artifacts reproduce third-party content where noted: WildSongBench
  prompts/lyrics and the frozen evaluator bundle are owned by their authors
  (m-a-p / YuE2 team); model weights follow their own Hugging Face licenses.
  See §9 and [`docs/PUBLIC_SECURITY_REVIEW.md`](docs/PUBLIC_SECURITY_REVIEW.md).
- Thanks to the YuE2 authors (`m-a-p`) for publishing the model, the WildSongBench
  benchmark and the frozen evaluator; to `yiakwy-xpu-ml-framework-team` for the
  `yue2` SGLang/Omni integration work these experiments build on and for hosting
  our contribution PRs; and to the SGLang project.
- Independent verification of the work above was performed by separate reviewer
  agents; their verbatim verdicts are preserved under
  [`reviews/`](reviews) and
  [`INDEPENDENT_REVIEWS_VERBATIM.md`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/40bd59f94079345917b526a3e2ee49c8a9f1f867/reports/final_merge_closure/INDEPENDENT_REVIEWS_VERBATIM.md).
