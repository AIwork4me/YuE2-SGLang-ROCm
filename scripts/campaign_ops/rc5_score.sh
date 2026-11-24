#!/usr/bin/env bash
# rc5_score.sh — OFFICIAL WildSongBench scoring under the GPU ownership lock
# (RC5 M5). Runs the frozen evaluator (hash-gated patched tree) exactly as the
# dataset README documents, with the disclosed ROCm portability patches active
# via WSB_ROCM_TORCH_OVERRIDE=1 (torch-family env exemption + qwen_asr
# transformers ASR backend). Scoring math, selection and aggregation are the
# evaluator's own code and are not modified here.
#
# Usage:
#   bash scripts/campaign_ops/rc5_score.sh <run_dir> <out_name> <mode> <metrics> [per_results_jsonl]
#     mode    : standard | shard      (standard needs all 384 rows)
#     metrics : e.g. per,songbench    or  mulan,allmusiccaps
#   per_results_jsonl : optional --per-results for the second command
#
# The GPU is held for the whole scoring run (gpu_lock.py); the lock holder
# keeps it while the evaluator's child processes drain.
set -uo pipefail

WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ROOT="${YUE2_EVALUATOR_TREE:-$WS/benchmark/wsb_metrics}"
PY_B="${YUE2_VENV:-$WS/environments/yue2-gfx1100}/bin/python"
[ -x "$PY_B" ] || PY_B="$(command -v python3)"
RUN_DIR="${1:?run_dir}"
OUT="${2:?out_name}"
MODE="${3:?mode}"
METRICS="${4:?metrics}"
PER_RESULTS="${5:-}"
RUN_DIR="$(cd "$RUN_DIR" && pwd)"
LOG_DIR="$RUN_DIR/scoring_logs/${OUT}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$LOG_DIR"
[ -f "$ROOT/wsb_eval.py" ] || { echo "FATAL: evaluator tree missing: $ROOT" >&2; exit 2; }

# integrity gate before any scoring: the evaluator must be the pinned patched state
WSB_EVAL_SHA="$(sha256sum "$ROOT/wsb_eval.py" | cut -d' ' -f1)"
[ "$WSB_EVAL_SHA" = "efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015" ] || {
  echo "FATAL: evaluator wsb_eval.py is not the pinned patched state ($WSB_EVAL_SHA)" >&2; exit 2; }

ARGS=(score --input "$RUN_DIR/evaluation_inputs.jsonl" --output "$RUN_DIR/$OUT"
      --mode "$MODE" --metrics "$METRICS")
[ -n "$PER_RESULTS" ] && ARGS+=(--per-results "$PER_RESULTS")

echo "[rc5-score] run=$RUN_DIR out=$OUT mode=$MODE metrics=$METRICS lock_wait=${RC5_GPU_LOCK_WAIT_S:-7200}" | tee -a "$LOG_DIR/score.log"
cd "$ROOT/.."   # documented layout: the evaluator is invoked from its parent
"$PY_B" "$REPO/scripts/gpu_lock.py" wait --who "rc5-scoring:${OUT}" \
  --wait-s "${RC5_GPU_LOCK_WAIT_S:-7200}" --poll-s 5 -- \
  env WSB_ROCM_TORCH_OVERRIDE=1 python3 "$ROOT/wsb_eval.py" "${ARGS[@]}" >> "$LOG_DIR/score.log" 2>&1
rc=$?
echo "[rc5-score] evaluator rc=$rc (log: $LOG_DIR/score.log)" | tee -a "$LOG_DIR/score.log"
for m in $(echo "$METRICS" | tr ',' ' '); do
  [ -f "$RUN_DIR/$OUT/$m.log" ] && { echo "--- $m.log tail ---"; tail -4 "$RUN_DIR/$OUT/$m.log"; } >> "$LOG_DIR/score.log"
done
exit $rc
