# Upstream Readiness

**Publication gate: CLOSED. Nothing has been posted to sgl-project/sglang;
PR #42106 has received no comment from this effort. Owner approval of the
final reviewed report is required first.**

## Ready now

- Patch series A (SGLang, 0001–0005): minimal, documented, regression-tested;
  on NVIDIA the diff is behavior-neutral by construction (guards under
  `_is_hip`, gates that return True on supported SM, try/except around a call
  that succeeds on CUDA).
- Reproduction scripts: environment build (clean-room verified), server
  launch, drivers, finalizer, auditors — all path-configurable, in the
  evidence repo.
- Evidence chain: phase reports ×6, independent review verdicts ×7, integrity
  manifests, evaluator patch audit with same-audio determinism data.

## Blocked on the full run (Phase 6 → 7 → 8)

- The 384-candidate table (SongBench / PER / MuLan / AllMusicCaps) and the
  H800-reference comparison with disclosed deltas — the PR comment draft's
  placeholders remain until these numbers exist and pass review.
- Performance summary (batch-1 walls, stage split, peak memory).

## Known open items (will be stated upstream, not hidden)

1. Evaluator environment substitution (torch 2.10.0+rocm7.14.1; ASR via
   transformers backend) — equivalence with CUDA/vLLM unverified and
   unclaimed; batch-composition sensitivity measured and disclosed.
2. Empty-transcript ASR failure mode observed once in 10 pilot candidates;
   final count reported with the full run.
3. Q3O not run (flash_attn 2.8.3 + 80 GB GPU requirement).
4. Same-seed byte-identical repeats observed on our stack — recorded as an
   observation of the reference-sampler configuration, not a general
   determinism claim (the PR itself notes H800 split-K nondeterminism).

## Checklist before requesting owner approval

- [ ] 384/384 verified (auditor verdict FULL)
- [ ] Official scoring completed for per, songbench, mulan, allmusiccaps
- [ ] Selection audited for all 192 prompts
- [ ] Comparison table + performance summary filled and reviewed
- [ ] Three-role final review (ROCm technical / scientific benchmark /
      maintainer simulation) with no open P0/P1
- [ ] PR comment draft free of placeholders
- [ ] Owner review and explicit approval
