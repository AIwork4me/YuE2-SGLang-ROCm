# YuE2 × SGLang × AMD ROCm — gfx1151 WildSongBench Reproduction Evidence

> **STATUS: WORK IN PROGRESS** — This repository records an independent
> reproduction of the YuE2 SGLang PR [sgl-project/sglang#42106](https://github.com/sgl-project/sglang/pull/42106)
> on AMD ROCm (Ryzen AI MAX+ PRO 395, Radeon 8060S, **gfx1151**) against the
> official [WildSongBench](https://huggingface.co/datasets/m-a-p/WildSongBench)
> benchmark. Nothing here claims AMD support in upstream SGLang. No results are
> final until the final review is merged.

## Mission

Reproduce the full official WildSongBench protocol (192 prompts × 2 candidates,
`cot=full`, frozen evaluator, PER-based best-of-2 selection) with SGLang PR
#42106 on gfx1151 under Linux-native ROCm, compare against the upstream H800
results, and prepare an upstream-ready report. Correctness before performance;
every claim must have evidence.

## Layout

- `reports/` — per-phase engineering reports (PHASE0 … PHASE9, FINAL)
- `evidence/` — machine-readable artifacts (environment, manifests, scores)
- `reviews/` — independent subagent verification verdicts per phase
- `scripts/` — reproduction scripts (setup, generation drivers, verification)
- `patches/` — minimal, documented ROCm compatibility patches
- `tests/` — targeted unit/integration tests
- `upstream/` — PR comment draft and handoff documents (NOT published)

## Source-of-truth pins

| Item | Revision |
|---|---|
| SGLang PR #42106 head (initial) | `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` |
| PR base | `ba68306256d64c53d302dc5d2f3be9e388af0738` |
| YuE2 authors' validated commit | `e0683229e755d60af70ad52af036e6386a8d60d1` |
| AR model | `m-a-p/YuE2-3B` (revision pinned in evidence/model_manifest.json) |
| VAE decoder (benchmark) | `m-a-p/YuE2-Vae-legacy` @ `b54118f0fc462f08999d1ec07e88817f4ee3f770` |
| WildSongBench dataset | revision pinned in evidence/protocol_lock.json |
| PyTorch | `2.12.0+rocm7.14.1` (AMD wheels, `repo.amd.com/rocm/whl-multi-arch`) |

## Phase status

| Phase | Topic | Status |
|---|---|---|
| 0 | Environment capture | PASS (reviews/PHASE0_REVIEW.md) |
| 1 | ROCm 7.14.1 environment | PASS (reviews/PHASE1_REVIEW.md) |
| 2 | Source + benchmark integrity | PASS (reviews/PHASE2_REVIEW.md) |
| 3 | ROCm compatibility RCA + patches 0001–0005 | PASS (reviews/PHASE3_REVIEW.md) |
| 4 | First end-to-end audio (HTTP) | PASS (reviews/PHASE4_REVIEW.md) |
| 5 | WSB pilot (5 prompts × 2, official shard scoring) | PASS (reviews/PHASE5_REVIEW.md) |
| 6 | Full 384-candidate generation | RUNNING (checkpoints in evidence/) |
| 7 | Official scoring (env ready; Q3O NOT RUN — flash_attn/CUDA) | pending full run |
| 8–12 | comparison, perf, final reviews, upstream package | pending |

Environment constraints recorded: huggingface.co unreachable (hf-mirror.com
used); github.com intermittently reachable (retry strategy documented).
