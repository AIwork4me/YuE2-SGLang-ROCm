# 07 — YuE2 author collaboration package (index)

Assembled 2026-11-19. Nothing here is submitted; all items are
owner-reviewable packages. Author approval is NOT claimed or implied
anywhere.

## Package 1 — PER cross-evaluator investigation
- `03_PER_CAUSAL_ANALYSIS.md` (cross-arm decomposition, exact denominators,
  paired statistics, hypothesis ledger)
- `03_PER_CROSS_EVALUATOR_MATRIX.csv` (A1/B1/G1 done; A2/B2/C1/C2 blocked-external)
- `03_CUDA_REFERENCE_HANDOFF.md` (executable CUDA-side kit, pre-registered
  interpretation table)
- `03_AUDIO_TRANSFER_MANIFEST.json` (384 × Arm A: ids/seeds/SHA256; audio
  itself stays private, transfer requires owner + author agreement)
- Planned on campaign completion: Arm B manifest + B1′ scoring receipts.

## Package 2 — Official baseline & protocol agreement
- `03_OFFICIAL_BASELINE_COMPARISON.json` (machine-readable, per-arm CIs)
- Requests 3/4/5 of `07_AUTHOR_REVIEW_REQUEST.md` (evaluator commit
  identity, ±2 pp tolerance confirmation, selection/capping semantics).

## Package 3 — SGLang ROCm patch reconciliation
- `07_UPSTREAM_PATCH_MATRIX.md` (live states of sgl#42106, omni#2540,
  yiakwy#1/#2; patch ownership analysis; submission gates)
- `patches/` (0001–0010 + audits), all chain-verified on this image.

## Package 4 — Runtime defect findings (to be finalized after M4 GPU windows)
- Arm B acceptance lifecycle fixes (this session, PR #14) with 16-scenario
  real-subprocess test suite — relevant to both omni PRs' serving paths.
- AR-stage hang (M4.1), HIP IMA single-tenant boundary (M4.2), native
  `close()` memory behavior (M4.3): scheduled post-campaign; evidence
  packages will attach here. No root-cause claims made yet.

## Package 5 — Publication claims & technical review
- To be assembled in M8 (`08_AMD_BLOG_TECHNICAL_DRAFT.md`,
  `08_PUBLICATION_CLAIMS_MATRIX.csv`): every published number → evidence
  path; authors + AMD review checklist embedded.

## Package 6 — Benchmark audio/data sharing authorization
- Explicit ask in `07_AUTHOR_REVIEW_REQUEST.md` item 1; licensing note:
  WSB lyrics performances are research-use; private-channel transfer only;
  never the public repository (M6 PASS enforces this scanning-side).

## External dependency ledger (owner-actionable)

| ID | Depends on | Exact ask | Blocks |
|---|---|---|---|
| EXT-1 | YuE2 authors | score our audio on CUDA (or accept private audio transfer) | R4 (PER closure) |
| EXT-2 | YuE2 authors | per-song reference receipts or reference audio (C1/C2) | R4 (strongest form) |
| EXT-3 | YuE2 authors | evaluator commit + tolerance confirmation | R4/R6 wording |
| EXT-4 | AMD reviewers | blog technical review | R10 |
| EXT-5 | owner | private transfer channel decision (HF private dataset vs other) | EXT-1 execution |
| EXT-6 | (optional) MI300X access | Q3O official judge memory requirement | Q3O metric (may remain NOT_TESTED by agreed scope reduction) |
