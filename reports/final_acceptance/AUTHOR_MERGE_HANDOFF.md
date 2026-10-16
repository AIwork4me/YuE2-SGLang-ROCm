# AUTHOR MERGE HANDOFF — Phase 7 (2026-10-16)

Target: integration of AMD ROCm support (gfx1100) into the YuE2 author's
`add_yue2` line and progression of the official Omni PR.

## 1. What is proved (direct evidence, independently audited)

- **Real W7900 HTTP E2E PASS** — real `sgl-omni serve` on gfx1100
  (ROCm 7.14.1, torch 2.12.0+rocm7.14.1), real `POST /v1/audio/speech`,
  valid WAV audio; evidenced in the PR #1 thread and the evidence repo.
- **Full official WildSongBench 384/384** — 192 prompts × 2 candidates,
  run `omniwsb20261014T1323Z`, strict audit 384/384 complete,
  5 truncated-but-valid, 0 missing/invalid; official frozen evaluator.
- **Quality**: SongBench Global Avg **6.730** (full 384) / **6.732**
  (selected 192); PER 0.24819 / 0.17608 (selected); MuLan 0.5080; AMC 0.4060
  (PER-selected candidates reused). All re-derived from per-song rows during
  the 2026-10-16 evidence audit — unchanged.
- **Serving evidence** — BS=1 P50 217 s, client E2E RTF 0.975 (speed 1.030×),
  sweep C=1..8 with RPS constant 0.0046 (serial GPU execution, honest negative
  result on client-concurrency scaling), 0 errors; corrected metric labels
  published as an explicit erratum.
- **Evidence integrity** — pilot (20) / full main pass (382) / prompt-164
  resume (2) / aggregate 384 cleanly separated; SHA256 anchors verified;
  machine-readable manifest; regression tests freeze the invariants.

## 2. What is not proved

- **NVIDIA H800 verification of the PR head** — not performed by us; we have
  no H800 access and make no CUDA-hardware claim. Requested from the author.
- **Official upstream merge** of sgl-project/sglang-omni#2540 — maintainer
  decision, not claimed.
- FA2/AITER acceleration on ROCm — intentionally out of scope (validated ATen
  attention retained; FA2 seqused_k investigation documented as BLOCKED).

## 3. What is awaiting the author

1. **H800 smoke** of the exact reviewed PR #1 head `eca7770f` in their NVIDIA
   CUDA environment: run real `sgl-omni serve`, POST `/v1/audio/speech`,
   confirm valid audio and that existing optimized CUDA paths execute;
   record source SHA + evidence. (Cross-GPU audio SHA equality is NOT
   expected or requested.)
2. **Merge PR #1** (ROCm reference path; maintainer feedback already
   "LGM after updating the comments"; comment-only update `eca7770f` pushed).
3. **Review/merge PR #2** (long-lyrics fix, `4ad6658b`, single commit on
   their current `add_yue2` head 85ae4b73) — passes 3 independent reviews
   (HTTP contract / security / regression), no P0/P1.
4. **Progress sgl-project/sglang-omni#2540** after the above.

## 4. Which exact PRs should be merged

- yiakwy-xpu-ml-framework-team/sglang-omni **#1** — head `eca7770f`
  (`fix(yue2): enable ROCm reference path without regressing CUDA fast paths`).
- yiakwy-xpu-ml-framework-team/sglang-omni **#2** — head `4ad6658b`
  (`fix(yue2): allow full-song lyrics in speech requests`).

## 5. Optimization tasks intentionally deferred (merge first, optimize later)

- ROCm FA2/flash-attention kernels (seqused_k blocker documented).
- AITER integration; ROCm TopK kernels.
- True GPU batched synthesis (author's MIGRATION.md ~3.2× estimate) —
  our data shows client-side concurrency alone adds zero throughput.

## 6. Public communication state

- 2026-10-16 11:25Z: full WSB results comment (issuecomment-6214464204).
- 2026-10-16: erratum comment (issuecomment-6218008055) — metric labels,
  GPU-util provenance, evidence archive clarity, PR #2 pointer; fact-checked
  pre-publication; quality scores explicitly unchanged.
- AUTHOR_HANDOFF_MESSAGE.md prepared (below) — **held, not posted**: the
  erratum already carries the genuinely new information (corrections + PR #2).
  The handoff ask (H800 + merges) was made on Oct 13 and remains open; the
  message is ready to post verbatim when the author replies, or if a
  consolidated follow-up becomes appropriate later. No comment spam.

## 7. Release states (evidence-backed only)

| State | Status |
|---|---|
| AMD_ROCM_QUALITY_VERIFIED | YES — 384/384 official WSB, scores re-verified |
| AMD_ROCM_SERVING_VERIFIED | YES — HTTP E2E + BS=1/sweep, corrected labels |
| EVIDENCE_INTEGRITY_VERIFIED | YES — Phase 1 forensic audit, independent |
| LONG_LYRICS_FIXED | YES — PR #2 delivered, 3× independent review PASS |
| NVIDIA_H800_VERIFIED | NO — awaiting author |
| AUTHOR_BRANCH_INTEGRATED | NO — awaiting author merge |
| OFFICIAL_OMNI_MERGED | NO — awaiting maintainers |
