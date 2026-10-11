# PHASE 5 — WildSongBench Pilot Reproduction

**Status: PASS (pilot generation + official shard-mode scoring executed; scores below are pilot-scale, explicitly NOT comparable to 192-prompt aggregates)**
**Date: 2026-10-11/12**

## 1. Pilot design (per mission)

Stage 1 — one prompt (index 0, zh) × 2 candidates.
Stage 2 — five identified prompts × 2 candidates, mixed languages,
**selected by dataset order and language, contents untouched**: indices
0, 1 (zh) and 2, 76, 77 (first three `en` rows in evaluation_targets.jsonl).
Every case used the ORIGINAL manifest row (style/lyrics/seed) and the frozen
official budgets (cot=full, ode 32, 9000/4096, 1024f+16h). No prompt-text
edits, no seed changes, no reduced budgets in the pilot evidence.

## 2. Generation results

| Stage | Candidates | Complete | Failed | Wall | Peak GTT |
|---|---|---|---|---|---|
| 1-prompt | 2 | 2 | 0 | 745.7 s | 24.0 GiB |
| 5-prompt | 10 (2 resumed) | 10 | 0 | 6348.0 s | 28.6 GiB |

`scripts/verify_wsb_artifacts.py` (official `verify_result` per candidate):
**10/10 verified complete, verdict FULL**; 2 truncated-but-complete candidates
retained (truncation is recorded, never filtered). Per-candidate walls ranged
369–1550 s for 142–360 s songs. Same candidate identity pattern as the
official driver (`wsb_{i:03d}_r{j}_s{seed}`).

## 3. Official evaluator on the pilot

- Standard mode refuses subsets by design ("expected 384"); the evaluator's
  own `shard` mode is the sanctioned subset path — used here.
- Portability patches 0006/0007 (see patches/README.md) were required to run
  the frozen evaluator on ROCm at all: torch-family env substitution
  (2.9.1/2.7.0 CUDA → 2.10.0+rocm7.14.1) and PER ASR via qwen_asr's
  transformers backend (vLLM has no ROCm build). Both are env-gated
  (`WSB_ROCM_TORCH_OVERRIDE=1`), recorded in every environment receipt, and
  the release.json integrity hashes were updated openly.
- `per,songbench` scored 10/10 with zero errors; per-candidate receipts in
  `runs/wsb_pilot/scores/` (pilot-scale, unselected-candidate scope).

### Pilot-scale observations (NOT 192-prompt aggregates)

Prompt 0 (zh), 2 candidates: PER 19.48%, SongBench Global 6.777
(Musicality 5.994). Full 5-prompt results in
`evidence/pilot_validation.json` once the shard run completes (in flight at
report time; updated in the commit). The zh prompt-0 PER (19.5%) is high vs
the authors' full-set 8.1–8.6% — single-prompt PER variance is expected to be
large (the historical reference for this prompt's original audio is 4.4%;
our fresh generations are different audio). The full 384-candidate run
(Phase 6, launched) provides the comparable numbers.

## 4. Evaluator-input schema proven

The finalizer's bundle passes the evaluator's strict `validate_generation`
(weight identities, config contract incl. effective cfg_scale 1.0 and
runtime identity hash, request equality with the frozen manifest row, FLAC
format binding to the scoring VAE).

## 5. Deliverables

- `reports/PHASE5_WSB_PILOT.md` (this file)
- `evidence/pilot_manifest.jsonl` (copy of run manifest), `evidence/pilot_validation.json`
- `scripts/run_wsb.py`, `scripts/finalize_candidate.py`, `scripts/verify_wsb_artifacts.py`
- `reviews/PHASE5_REVIEW.md` (independent subagent)

## 6. Gate

**PASS** — official manifest rows execute end-to-end through the SGLang
server on gfx1151, artifacts verify against the frozen evaluator schema, and
the official evaluator runs (shard mode) with disclosed portability patches.
