# M4.9 — Official CUDA Evaluator Alignment (Q3O & PER)

## Status

`Q3O_OFFICIAL_EQUIVALENCE_NOT_ESTABLISHED`
`PER_OFFICIAL_CUDA_COMPARISON_BLOCKED_EXTERNAL`

No owner-authorized CUDA host exists for this mission; no author-provided
real CUDA evaluation receipts were received. No CUDA numbers are fabricated
anywhere in this repository.

## What is prepared and self-tested (ready to execute on a CUDA host)

1. **Same-audio comparison package** — the frozen S_V selection manifest
   (04_Q3O_CORRECTED_SELECTION_MANIFEST.json) binds, per candidate: audio
   bytes (sha256), target identity, judge weights revision + content
   hashes, prompts, decoding, parser and aggregation. A CUDA host can score
   the EXACT same 192 audio files with the official evaluator.
2. **Pre-registered comparison criteria** (frozen BEFORE any CUDA run;
   see reports/developer_reference/author/CUDA_Q3O_RUNBOOK.md and
   CUDA_PER_RUNBOOK.md): per-candidate score differences, mean paired
   delta, median absolute delta, P95 absolute delta, score correlation,
   component-level differences, coverage, failure cases, routing behaviour
   where observable. Both BIAS and ABSOLUTE AGREEMENT must be reported —
   high correlation alone is not equivalence.
3. **Comparator tooling** (RC6, self-tested twice): per-candidate diff
   machinery for Q3O receipts and PER handoff package for the ASR arm.
4. **Official environment reference** (from the frozen evaluator bundle):
   vLLM 0.14.0 CUDA + FlashAttention 2.8.3; the official engine revision is
   re-verified against the bundle at execution time, not assumed.

## PER official CUDA comparison

The existing handoff package (RC6 author package, CUDA_PER_RUNBOOK.md)
remains the path: same audio, same official scorer, the official vLLM
0.14.0 ASR engine on CUDA. The 2x2 PER attribution
(T/V × S_T/S_V) quantified the engine-path effect (-8.18pp) on OUR engines;
the official-CUDA column remains open until a host exists.

## Discipline

- No paper value is used as an optimization target.
- Until the CUDA runs exist, the difference RCA (04_Q3O_DIFFERENCE_RCA.md)
  keeps judge-implementation vs generation-quality decomposition OPEN.
