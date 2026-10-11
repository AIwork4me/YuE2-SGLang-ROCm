# PHASE 7 — Official WildSongBench Scoring (plan + status)

**Status: IN PROGRESS — evaluator environments validated on ROCm (pilot-scored); full-run scoring executes after Phase 6 completes.**

## 1. Environment (built and validated)

- Frozen evaluator bundle `evaluation/wsb_metrics.tar.gz` extracted and
  verified (`release.json` code-file hashes; updated openly for patches
  0006/0007).
- `prepare --metrics per,songbench,mulan,allmusiccaps --download hf-mirror
  --install` completed (RC=0): pinned venvs (Python 3.12.11) + evaluator
  weights (Qwen3-ASR-1.7B @ 7278e1e7, SongBench stack, MuQ-MuLan,
  AllMusicCaps) at fixed revisions with SHA checks.
- **ROCm portability (patches 0006/0007, env-gated
  `WSB_ROCM_TORCH_OVERRIDE=1`)**: torch-family swapped to
  2.10.0+rocm7.14.1 in the metrics/eval venvs (no ROCm build exists of the
  pinned 2.9.1/2.7.0 CUDA wheels) and PER's ASR runs on qwen_asr's
  transformers backend (vLLM 0.14.0 is CUDA-only). Receipts record actual
  versions; all other packages match the lock exactly. Validated by scoring
  the Phase 5 pilot (zero errors, sane values).

## 2. Scoring protocol (official, unchanged)

1. `wsb_eval.py score --input runs/wsb_full/evaluation_inputs.jsonl --output
   runs/wsb_full/scores --mode standard --metrics per,songbench`
2. `wsb_eval.py score --input runs/wsb_full/evaluation_inputs.jsonl
   --per-results runs/wsb_full/scores/per_song.jsonl --output
   runs/wsb_full/additional --metrics mulan,allmusiccaps`

Standard mode enforces 384-candidate completeness and applies the frozen
PER-based best-of-2 selection (min PER → min edits → min |phoneme-count
diff| → min candidate_index) across every metric. Selected means land in
`runs/wsb_full/scores/summary.json` under `standard_selected.groups.all`.

## 3. Q3O feasibility verdict: NOT RUN

Blockers (per the mission's feasibility gate):
1. The Q3O scorer hard-requires `flash_attn==2.8.3` (CUDA-only kernel
   library; no ROCm build) — `RuntimeError('Q3O protocol requires
   FlashAttention 2.8.3…')` on any ROCm host.
2. Q3O runs Qwen3-Omni-30B-A3B; the official documentation requires an
   80 GB GPU. This system has 32 GiB dedicated VRAM (100 GiB GTT unified
   pool; the model would spill to system RAM with unusable latency and the
   flash-attn blocker stands regardless).

Q3O is recorded as **NOT RUN — unsupported on this platform** and excluded
from any all-metrics PASS claim. It remains a separately-scoped follow-up
(if a ROCm flash-attn appears upstream).

## 4. Planned outputs (after Phase 6)

`evidence/official_scores.json` (both summary.json files verbatim +
extraction), `evidence/per_prompt_scores.csv`, `evidence/selection_audit.json`
(selected indices + tie-breaks from per_song.jsonl),
`evidence/evaluator_environment.json` (venv receipts incl. the disclosed
ROCm substitution).

Scoring completeness will be reported per metric: expected 192 selected /
actual / failed / omitted — never presenting a partial aggregate as the
full-dataset result.
