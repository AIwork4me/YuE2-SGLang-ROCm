# 04_Q3O_CONTRACT.md — RC6 A4: Qwen3-Omni (Q3O) judge contract

## What the ROCm-adapted judge IS (verified against code and receipts)

| Contract element | Verified state |
|---|---|
| Model | `Qwen/Qwen3-Omni-30B-A3B-Instruct@26291f79…` (Thinker-only, BF16), content-hashed into `identity.json` (`identity_sha256 e8e2b7a2…`) |
| Official prompt | official open-format judge prompt, sha-pinned in `identity.json` (`evaluator_release_sha256`, per-file `evaluator_runtime_sha256` map) |
| Official parser | official `eval_control` parser verbatim (sha-pinned) |
| Scoring aggregation | official `PaperQ3OScorer.score()` verbatim; WSB-paper-Control-20260905 frozen candidate weights, sha-checked per row (1536 rows) |
| Placement | 34 GPU + 14 CPU MoE layers; GPU = **stock HF bf16 experts + in-place stable top-k forward patch** (`install_stable_topk_gpu_moe`: the ONE change is `_topk_stable`; routing weights still cast to hidden bf16 exactly as stock HF); CPU = `CpuResidentMoeBlock` fp32 arithmetic with pinned bf16 rounding points |
| Tie-break | lowest expert index via stable argsort over fp32 softmax of bf16-rounded router logits (mutation-pinned: R3/R4 killed) |
| Receipts | per-candidate `receipts/<id>/q3o.json` binding generation_id, audio path/bytes, judge model, dimension scores+weights, raw judgement, token hashes, timing, VRAM |
| Coverage | 192/192 valid, 0 failed, 0 parser failures (RC5.1 full run, frozen) |

## What it is NOT

- It is **not the official engine**: the official judge runs vLLM 0.14.0 +
  FlashAttention 2.8.3 on CUDA. `RC5_Q3O_GPU_MOE=batched`
  (`BatchedGpuMoeBlock`) is an **EXPERIMENTAL, NOT_DEFAULT** packing path
  (fails to load on 48 GB in the full-model configuration; code retained for
  the record) — never part of a published score.

## Determinism vs equivalence (A4.2)

Three distinct claims, never conflated:

| Claim | Status | Evidence |
|---|---|---|
| WITHIN_ENGINE_REPEATABILITY | **PASS** | 5 runs / 2 processes (incl. full model reload): identical generated-token hashes and identical scores (4.833333 pilot) |
| CROSS_ENGINE_NUMERICAL_EQUIVALENCE (vs official CUDA vLLM judge) | **NOT_ESTABLISHED** (BLOCKED_EXTERNAL: no CUDA host) | different attention kernels + unknown official tie rule |
| CROSS_BACKEND_SCORE_AGREEMENT | **NOT_MEASURED** | requires the same-audio CUDA run (runbook + comparator ready: `04_Q3O_COMPARISON_RUNBOOK.md`, `scripts/rc6_q3o_comparator.py`) |

## Tie-rate statement (exact denominators — A4.2)

Measured on REAL Thinker inference during repeatability runs (not synthetic):

- CPU blocks: 5,973 exact boundary ties / **32,550 routed token-slots** = 18.35%
- GPU blocks: 15,969 / **79,050 routed token-slots** = 20.20%

A "boundary tie" = k-th and (k+1)-th ranked fp32 softmax probability exactly
equal at a routed token-slot; the expert SET is then decided by the
tie-break rule alone. These are **routing-slot** statistics: they are NOT
"20% of tokens wrong" and NOT "20% of experts mis-chosen" — they bound how
much of the routing is decided by the (unpublished) tie rule of any other
kernel. Counts are bit-identical across all 5 runs (deterministic under our
stable tie-break).

## What may be reported publicly

- Q3O **coverage** (192/192) under the ROCm-adapted judge: reportable.
- Q3O **score** (4.393986/5): reportable ONLY labelled `ROCm-adapted`, with
  the engine difference and tie-rate disclosure attached; never mixed into
  an "official five-metric" claim and never averaged with official-engine
  numbers.
- Official equivalence: only after a same-audio CUDA comparison executed
  under pre-registered criteria (`04_Q3O_COMPARISON_RUNBOOK.md`).
