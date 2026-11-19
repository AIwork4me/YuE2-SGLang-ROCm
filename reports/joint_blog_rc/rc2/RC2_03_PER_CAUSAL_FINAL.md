# RC2_03 — PER causal analysis: RC2 addendum (interim; final closure = cross-evaluator cells)

**Status: PER_PARITY remains OPEN (BLOCKED_EXTERNAL for the decisive cells).**
This addendum adds three pieces of RC2 evidence to the M3 analysis
(`03_PER_CAUSAL_ANALYSIS.md`, unchanged and still authoritative for the
arm-paired findings) and corrects the external kit.

## 1. New controlled evidence: error DIRECTION (Arm A fresh, selected-192)

New analysis (`scripts/rc2_per_length_analysis.py`, official
`summary.selected_candidates` denominator, prompt bootstrap n=10 000;
aggregates only — no lyrics/transcript text in any artifact):

| Quantity | Value |
|---|---|
| net transcript length (hyp − ref, chars), mean | **−47.7** [−70.3, −28.5] |
| candidates net-negative / net-positive | **140 / 50** |
| empty transcripts (confirmed) | 3 |
| ASR-capped (selected) | 36 |
| Spearman ρ(PER, reference phoneme count) | +0.134 |
| Spearman ρ(PER, ASR output length) | −0.083 |
| Spearman ρ(PER, audio seconds) | +0.070 |
| PER zh / en (mean [CI]) | 16.49 % [14.3–18.8] / 16.61 % [13.2–20.5] |

**Finding 8 — the error is deletion-dominant.** Hypothesis transcripts are
systematically SHORTER than the references (CI excludes 0; 73 % of
candidates net-negative). Under-transcription (dropped words/lines) on the
ASR side is the dominant error mode, not hallucinated insertions. This is
*consistent with* H1 (ROCm ASR backend under-transcribes vs the official
CUDA serving) and *less consistent with* a generic generation-quality
degradation (which would also degrade the non-ASR judges — they reproduce:
Δ −0.027 / −0.010 / −0.004). Length effects on PER are weak (|ρ| ≤ 0.13):
the gap is not a length artifact.

Caveat (explicit): char-level net length is a DIRECTIONAL proxy, not a
phoneme-level I/D/S decomposition; the phoneme-level decomposition is
pre-registered as part of the cross-evaluator pairing (kit §return
artifacts). zh/en char semantics differ; the direction holds in both
language groups separately (per-lang JSON in `RC2_03_PER_LENGTH_EFFECTS_ARMA.json`).

## 2. CUDA kit audit — old procedure was NON-EXECUTABLE; corrected kit VALIDATED

Audit findings (see corrected runbook for detail): wrong invocation
(`python -m` on a non-package), mp3-only payload insufficient for the
official `standard` mode (full verified bundle required: result/request/
config/flac/npy — `verify_result` re-hashes everything and validates request
text against frozen WSB targets), layout mismatch with the scorer's
path resolution, missing `prepare --install` step.

**Validation executed on this host (CPU-only):** the pinned official
`wsb_eval.prepare_inputs()` accepted **384/384** real Arm A candidates in a
clean report directory — request/config/weights/FLAC verification and mp3
identity-receipt chain all PASS (17.5 min wall). The corrected procedure is
therefore proven against the exact artifacts the CUDA side will receive.
Full-bundle manifest (384 × per-file SHA256, ~15 GiB payload) generated;
receiving-side fail-closed verifier unit-checked on four corruption modes.

## 3. Hypothesis ledger delta (vs 03 §7)

| # | Hypothesis | RC2 delta |
|---|---|---|
| H1 ROCm ASR backend | **STRENGTHENED** — deletion-dominant direction + determinism + common-mode across stacks; still requires A2/B2 to close |
| H2 generation numerics | WEAKENED (direction + non-ASR judge parity), NOT EXCLUDED (no CUDA-side score of our audio yet) |
| H3 evaluator version drift | UNCHANGED (author request includes exact-commit ask) |
| H8 (new) length artifact | EXCLUDED — |ρ| ≤ 0.13, both langs; capping already excluded |

## 4. What still closes this (unchanged, now executable)

A2 (or B2/C1/C2) executed with the VALIDATED kit → pre-registered decision
table (8–11 % ⇒ H1; 16–18 % ⇒ H2; intermediate ⇒ paired co-factor split).
Acceptance target stays ±2 pp (provisional, pre-registered, author
confirmation requested — RC2_06).
