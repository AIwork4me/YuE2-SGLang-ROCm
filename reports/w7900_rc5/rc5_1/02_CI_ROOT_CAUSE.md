# RC5.1 P0.2 — Exact-HEAD CI Root Cause & Fix

## Failure (reproduced)

Latest failing runs (PR #19, HEAD `bb77317`):

- https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/45406248566
- https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/45406234890

```
ERROR collecting tests/test_rc5_q3o_moe.py
ModuleNotFoundError: No module named 'torch'
```

Local reproduction (torch import blocked via a meta-path finder, simulating
the torch-free CI interpreter) reproduces the identical collection error at
HEAD `bb77317`.

## Root cause

`tests/test_rc5_q3o_moe.py` executed
`spec.loader.exec_module(M)` at module top level; the loaded
`scripts/rc5_q3o_moe.py` imports torch at module scope. The per-test
`pytest.importorskip("torch")` calls cannot prevent a COLLECTION-stage
failure — pytest imports the test module before running any test function.
The lightweight `cpu` job installs no torch, so the whole module failed to
collect and the suite went red.

## Fix (minimal)

1. `tests/test_rc5_q3o_moe.py`: the module is now loaded lazily inside each
   test via `_module(torch)`; `_skip_without_torch()` wraps
   `pytest.importorskip` so both a missing torch and a broken torch install
   skip honestly with an explicit reason. Verified: torch-free run = 9
   SKIPPED with reason (no collection error); torch run = 9 PASSED.
2. New CI job `q3o-moe-cpu-numerics`: installs a pinned CPU wheel
   (`torch==2.12.0` from `https://download.pytorch.org/whl/cpu`) so the MoE
   numerics actually RUN on CI instead of skipping: stable top-k, boundary
   tie, expert identity, routing weights, weight normalisation, CPU-resident
   MoE, BF16 rounding points, HF-reference comparison, deterministic
   repeated execution, plus the mutation-control harness (CPU-applicable
   mutations; GPU-block mutations survive honestly on a CPU runner and the
   report records `gpu: false`). GPU cases SKIP on this runner and are never
   counted as GPU validation.

## Independent test-quality review findings (and closure)

- **Oracle dependence (found & fixed)**: `_oracle_output` previously called
  the module's own `_route()`. It now computes the reference independently:
  fp32 softmax of the bf16 router logits, top-k by a stable sort of the
  NEGATED probability (ties -> lower expert index — a different mechanism
  than the module's descending argsort+gather), fp32 renormalisation, bf16
  rounding, HF reference expert modules, fp32 sum. The routing rule itself
  is separately pinned against hand-written fixed tensors
  (`test_topk_stable_breaks_ties_by_lowest_index`) and the HF verbatim
  formulas (`test_route_matches_hf_formulas_on_tie_free_logits`).
- Numbers are asserted (ulp-level bf16 comparisons), not just shapes;
  tolerances are ulp-scale, inputs fixed by seeds; determinism asserted by
  repeated execution; GPU cases require `torch.cuda.is_available()` and skip
  otherwise.
- **Mutation suites are reported separately, never merged**: engineering
  mutation suite 38/38 KILLED (RC5, unchanged); Q3O MoE GPU mutation suite
  = **15/16 KILLED** on the W7900 host (torch 2.14.0+rocm10.1.0),
  `reports/w7900_rc5/rc5_1/02_Q3O_MOE_MUTATION_GPU.json`.
- **G2 (`routing weights kept in fp32`) survivor analysis**: at `top_k=1`
  G2 is exactly equivalent (bf16 rounding of an exact fp32 product of
  bf16-representable factors). At `top_k>1` it changes ~39% of token outputs
  by at most **0.61% of the global output scale** (bound: 2%), because the
  pinned path rounds each contribution to bf16 before the fp32 sum while
  the mutation rounds once — the same summation-freedom class the suite
  discloses for both blocks. Killing it would demand per-token bit-exactness
  at `top_k>1`, which no implementation of the disclosed fp32-sum design can
  satisfy. The mutation is retained; no test expectations were weakened or
  tightened to fabricate 16/16.

## Same-commit engineering fixes (P0.1 follow-through, disclosed)

- `scripts/rc5_generate.py`: SIGTERM tail-checkpoint gap fixed (candidates
  17-20 were left unarchived by the rc=143 pause); resume gate split into
  frozen identity / per-session paths / driver-revision pointer with
  `--allow-driver-update` (pure decision function `resume_decision`, unit
  tested in `tests/test_rc5_resume_gate.py`); `--checkpoint-only` mode.
- `scripts/rc5_backup.py`: restore now preserves the checkpoint history
  (archives + manifests, hash-verified) so a restored run does not
  re-archive every old candidate.
