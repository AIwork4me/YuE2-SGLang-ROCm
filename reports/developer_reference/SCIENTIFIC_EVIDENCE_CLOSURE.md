# SCIENTIFIC_EVIDENCE_CLOSURE.md — RC6 RC5.2 summary (entry point)

Every claim below is re-derived from live RC6 computation, not copied from
RC5.1. Machine-readable receipts live beside this file.

## 1. Generation determinism (A1)

- **380/384 FILE_BYTE_IDENTICAL** vs the frozen historical Arm B manifest
  (re-derived live).
- The 4 non-identical candidates: identical duration (1e-6 s), codec frame
  count, official seed, style/lyrics inputs, truncation flag; only FLAC
  container bytes differ (−2/+2/+15/0).
- Each of the 4 passes lossless self-consistency (decoded PCM MD5 ==
  STREAMINFO MD5) and same-build re-encode determinism; an ffmpeg
  different-encoder control proves that identical PCM yields different
  bytes across encoder implementations (encoder-build sensitivity
  demonstrated, mechanism class established).
- Historical FLAC artifacts are absent (image deleted) →
  `PCM_IDENTITY_UNVERIFIABLE_HISTORICAL_ARTIFACT_ABSENT`;
  `CONTENT_IDENTITY_NOT_ESTABLISHED` for the 4; never faked, never
  regenerated.
- RC6 addition: **cross-workspace same-seed byte-identity** (fresh clone
  reproduced the first song's FLAC bit-exactly).

## 2. Evaluator provenance & fail-closed resume (A2)

- Formal `ASR_RUN_IDENTITY` contract (model file hashes, engine, preproc
  sources, decoding, manifest, driver) embedded in every future receipt
  (`rc6_asr_identity.py`).
- The RC5.1 candidate-id-only resume defect is closed: fail-closed audit
  with REJECT/INCOMPLETE/FAIL taxonomy, tail quarantine, supersede-not-
  overwrite; scorer hardening (no bare asserts, duplicates/coverage/repeat/
  engine checks, denominator + aggregation audits; official PER math
  untouched — GREEN regression reproduces frozen E2 rows exactly).
- Both historical arms audited read-only: 384/384 audio match, 0
  violations; model hashes recomputed-now (disclosed).
- Verification: 20/20 offline negative controls + LIVE resume control
  (reuse only on exact identity).

## 3. PER causal attribution (A3)

Full 2×2 on the same 384 audios (03_PER_PAIRED_ATTRIBUTION.json):

| | S_T (frozen selection) | S_V (corrected selection) |
|---|---|---|
| **T (transformers)** | 17.7699% | 20.2042% |
| **V (vLLM 0.19.1)** | 9.5854% | 8.4488% |

- evaluator-path effect (fixed selection): −8.18 pp (dominant)
- selection effect under V: −1.14 pp; under T: +2.44 pp
- paper reference: 8.44% (official CUDA evaluator — not run here)
- Selection reconciliation (03_SELECTION_RECONCILIATION.json):
  **changed_prompt_count 60 · removed 60 · added 60 · symmetric difference
  120** — the historical "60 vs 120" confusion resolved with explicit
  fields; docs fixed.
- Corrected five-metric scoreboard (Scoreboard B) EXECUTED with the frozen
  official evaluator on S_V: SongBench **6.742109** · MuLan **0.504299** ·
  AMC **0.403000** · PER **8.4488%** (192/192 complete) — published
  separately, never mixed with Scoreboard A. Q3O-on-S_V NOT_RUN (budget
  disclosure).
- First-divergence: H10 stays OPEN (kernel-level arithmetic characterized,
  not isolated); bounded follow-up pre-registered.

## 4. Q3O scientific boundary (A4)

- Contract verified against code + receipts (official prompt/parser/
  weights verbatim; 34 GPU + 14 CPU MoE; stable tie-break; 5-run
  token-identical).
- Determinism ≠ equivalence: WITHIN_ENGINE_REPEATABILITY PASS ·
  CROSS_ENGINE_NUMERICAL_EQUIVALENCE NOT_ESTABLISHED ·
  CROSS_BACKEND_SCORE_AGREEMENT NOT_MEASURED (comparator ready + self-
  tested twice, incl. live receipts).
- Tie-rate denominators stated exactly (18.35% CPU / 20.20% GPU of routed
  token-slots — never "20% of tokens wrong").
- Mutation survivor G2 classified: EXPERIMENTAL_NOT_DEFAULT path +
  disclosed rounding-point deviation class; NOT_FIXED, no tolerance tuning;
  zero effect on published results (validated run used the default path).

## 5. What remains scientifically open (never hidden)

- Official CUDA comparisons (PER + Q3O): BLOCKED_EXTERNAL — handoff
  packages, runbooks and pre-registered criteria templates ready
  (author/).
- Q3O official tie-break rule: unknown (author question A10/B6).
- H10 kernel-level loop trigger: OPEN with a bounded follow-up plan.
- Historical PCM identity for the 4 FLAC-divergent candidates:
  unprovable (artifacts absent).
