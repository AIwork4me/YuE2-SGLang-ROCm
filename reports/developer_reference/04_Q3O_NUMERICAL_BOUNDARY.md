# 04_Q3O_NUMERICAL_BOUNDARY.md — RC6 A4.2: Q3O numerical boundary

## Where numbers can differ from the official CUDA judge

| # | Boundary | Our path | Official path | Impact class |
|---|---|---|---|---|
| 1 | Attention kernels | HF transformers 4.57.6 SDPA on ROCm | vLLM 0.14.0 + FlashAttention 2.8.3 CUDA | logits-level numeric drift, unbounded by analysis |
| 2 | MoE top-k tie-break | stable argsort, lowest expert index, deterministic | vLLM fused-MoE kernel rule (NOT published) | ~18–20% of routed slots are EXACT ties; the expert set at those slots is rule-dependent |
| 3 | Router-logits rounding | bf16 BEFORE routing (pinned by mutation C2/R2 killed) | bf16 weights (same class) | tie frequency depends on this rounding; pinned to stock HF semantics |
| 4 | Contribution summation dtype | expert outputs accumulated per stock HF (bf16 sequential `index_add_`) on GPU; CPU blocks fp32 with pinned bf16 rounding points (disclosed) | fused kernel fp32 accumulate, single final round | disclosed deviation of BOTH our blocks; deliberately not a mutation control (RC5.1 note) |
| 5 | Thinker-only BF16 weights | same weight files (content-hashed) | same | none |

## What is pinned (and how)

- bf16 router-logits rounding before routing — mutation C2 (CPU) and R2
  (softmax precision) are KILLED by bit-exact tests.
- top-k weight normalisation — mutation R1 KILLED.
- stable tie-break (lowest index) — mutations R3 (stock torch.topk) and R4
  (unstable argsort) KILLED, including on the default in-place GPU patch.
- routing weights cast to hidden bf16 on the DEFAULT GPU path
  (`rw = rw.to(hs.dtype)` — stock HF semantics preserved; verified by code
  audit, covered by the patch-path tests).
- 5-run/2-process token-level identity (WITHIN_ENGINE_REPEATABILITY).

## What is explicitly NOT claimed

- Per-token expert-choice equivalence (~20% of routed slots are exact ties
  decided by an unpublished rule).
- Score-level equivalence (unmeasured without CUDA).
- The pilot's 4.833333 vs full 4.393986 are different candidate sets —
  never compared directly.

## Resource boundary (48 GiB card, frozen RC5.1 profile)

Peak VRAM 42.41 GiB (torch allocations) · host VmHWM 49.83 GiB under a
55 GiB cgroup limit (5.17 GiB headroom) · mean 87.1 s/candidate ·
total 4.65 h for 192. The batched-packing GPU MoE mode cannot LOAD on
48 GB (root-caused: transposed copies + list transients + reference
cycles/allocator fragmentation) — the validated path is the in-place
stable top-k patch over stock HF experts.
