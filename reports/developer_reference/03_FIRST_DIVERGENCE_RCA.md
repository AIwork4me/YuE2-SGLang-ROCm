# 03_FIRST_DIVERGENCE_RCA.md — RC6 A3.4: bounded first-divergence investigation

## Status: H10 remains OPEN (honestly), with the boundary sharpened

RC5.1 already localized the ASR engines' divergence to the decode path with
a same-audio, same-weights matrix (E1–E8) and a step-level first-divergence
probe. RC6 did NOT extend the kernel-level hunt (bounded GPU budget was
allocated to fresh-clone verification, corrected scoreboard and controls —
a mission-level prioritization, recorded here). What stands:

### Established (RC5.1 evidence, re-audited in RC6)

- Input features are **bit-identical** across engines (probe receipts).
- Divergence appears in **greedy decode** after the language header:
  top-5 logits identical, EOS probability ~2e-5, step-8 near-tie flip
  (07_ASR_FIRST_DIVERGENCE.json).
- The failure is INVARIANT to precision (bf16/fp16/fp32), attention
  (sdpa/eager), batch size, and device (GPU/CPU) — the loop is a property of
  the transformers decode path on knife-edge logits, not of ROCm kernels
  per se.
- vLLM's decode path on the SAME weights + SAME GPU transcribes the same
  audio normally (E2 arm, 384/384).

### The causal attribution (closed at the path level)

The RC6 2×2 attribution (03_PER_PAIRED_ATTRIBUTION.json) quantifies the
decomposition on identical audio:

| Cell | micro PER |
|---|---|
| T(S_T) transformers, frozen selection | 17.7699% |
| V(S_T) vLLM, same frozen selection | 9.5854% |
| T(S_V) transformers, corrected selection | 20.2042% |
| V(S_V) vLLM, its own selection | 8.4488% |

- evaluator-path effect (fixed selection): **−8.18 pp** — the dominant factor
- selection effect (fixed evaluator V): −1.14 pp
- selection effect (fixed evaluator T): +2.44 pp (the frozen arm penalizes
  candidates selected for the other engine)
- total transition: −9.32 pp (the whole historical gap)

### What remains open (not inflated, not hidden)

- The **exact kernel arithmetic** that flips the knife-edge logits (which
  kernel's rounding differs) — characterized, not isolated. H10 OPEN.
- The **official CUDA vLLM 0.14.0 comparison** — BLOCKED_EXTERNAL; handoff
  package + runbook + pre-registered criteria ready (author/).
- We deliberately do NOT call the path-level finding a "kernel bug": the
  evidence supports an engine-path difference on near-tie logits; the
  specific operator arithmetic is unproven.

### Bounded follow-up (for a future GPU window)

Two-engine per-layer logits tracing on 2–4 minimal repro candidates
(both engines instrumented at matching decode steps) — budget ~2–4 h GPU;
pre-registered as the ONLY sanctioned way to close H10.
