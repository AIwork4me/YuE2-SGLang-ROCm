# Version Matrix

How the pieces fit together, which combination is verified on which hardware,
and where each number comes from. Companion locks: `configs/developer.lock.yaml`
(Profile A) and `configs/benchmark.lock.yaml` (Profile B).

## Stacks

| Layer | Profile A (developer) | Profile B Arm A (benchmark, native PyTorch) | Profile B Arm B (benchmark, SGLang) |
|---|---|---|---|
| Inference code | yue2 (YuE main) / yue2-infer latest wheel | yue2-infer **0.1.3** official wheel | SGLang PR #42106 @ `ced0ef7d` (**OPEN**, unmerged) + patches 0001–0005, 0008 |
| Backend | `YuE2Pipeline` public API | `--backend torch-eager` (DEV-1) | HTTP server, correctness-first ROCm flag matrix |
| torch | 2.10.0+rocm7.1 (pending verify for dev path) | 2.10.0+rocm7.1 (official pin) | 2.12.0+rocm7.14.1 (AMD multi-arch) |
| transformers | per package pin (4.57.6 for 0.1.3) | 4.57.6 | 5.17.0 |
| AR model | m-a-p/YuE2-3B (weights sha `1d55c42c…`) | same, rev `1a96eca6` | same, rev `1a96eca6` |
| VAE | YuE2-Vae (listening, default) | YuE2-Vae-legacy @ `b54118f0` (benchmark decoder) | same |
| Evaluator | n/a | frozen wsb_metrics + patches 0006/0007/0009 | same |

## Hardware × capability (evidence-backed)

| Capability | W7900 gfx1100 (this mission) | Radeon 8060S gfx1151 (historical) |
|---|---|---|
| torch matmul/SDPA (2.10+rocm7.1, 2.12+rocm7.14.1) | PASS | PASS (2.12+rocm7.14.1) |
| Official yue2-infer 0.1.3 torch-eager full song | PASS (pilot, prompt 0, 2/2) | NOT TESTED |
| SGLang yue2 server + HTTP generation | PASS (smoke) | PASS (384/384 campaign) |
| Full 384-candidate campaign | IN PROGRESS | PASS (SGLang arm, evidence/) |
| Official scoring (per/songbench/mulan/amc) | IN PROGRESS | PASS |
| Q3O | NOT TESTED (needs 80GB GPU) | NOT TESTED |

## Why two torch versions

The official YuE hardware doc pins torch 2.10.0 (non-macOS) and installs the
ROCm build from `download.pytorch.org/whl/rocm7.1`; we verified gfx1100 works
with it and use it for the official PyTorch benchmark arm. The SGLang campaign
stack froze torch 2.12.0+rocm7.14.1 from AMD's multi-arch index before this
mission (validated 384/384 on two GPUs); changing it now would break Arm B
comparability with the historical campaigns for no scientific gain.

## Provenance rules

1. Historical numbers (SongBench 6.718/6.731/6.730 etc.) cite
   `evidence/` (top level, gfx1151), `evidence/gfx1100/`, and branch
   `validation/gfx1100-rocm7141` — never re-measured, never edited.
2. New numbers cite `evidence/publication/` on
   `feat/yue2-rocm-publication-readiness` with run receipts.
3. A "PASS" here always names the evidence path; otherwise it is NOT TESTED.
