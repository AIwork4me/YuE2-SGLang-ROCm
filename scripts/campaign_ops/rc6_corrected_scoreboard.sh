#!/usr/bin/env bash
# rc6_corrected_scoreboard.sh — RC6 A3.3: five-metric re-scoring on the
# vLLM-corrected selection (S_V), Scoreboard B. Same official evaluator,
# same audio bytes, same aggregation code as the frozen Scoreboard A; ONLY
# the selection set differs (disclosed: selection driven by the vLLM
# corrected PER arm, not the frozen transformers arm).
#
# Writes ONLY into /data/yue2-runs/rc6-corrected-scoreboard (new run_id;
# frozen RC5.1 trees untouched).
set -uo pipefail
WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="/data/yue2/upstream/yue2-sglang-rocm"
ROOT="$WS/benchmark/wsb_metrics"
OUT_BASE="/data/yue2-runs/rc6-corrected-scoreboard"
PY_B="$WS/environments/yue2-gfx1100/bin/python"
[ -x "$PY_B" ] || PY_B="$(command -v python3)"

WSB_EVAL_SHA="$(sha256sum "$ROOT/wsb_eval.py" | cut -d' ' -f1)"
[ "$WSB_EVAL_SHA" = "efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015" ] || {
  echo "FATAL: evaluator wsb_eval.py is not the pinned patched state ($WSB_EVAL_SHA)" >&2; exit 2; }

mkdir -p "$OUT_BASE/logs"
LOG="$OUT_BASE/logs/score-$(date -u +%Y%m%dT%H%M%SZ).log"
{
  echo "[rc6-selv] input=$OUT_BASE/selv_input.jsonl (192 S_V rows, corrected selection)"
  sha256sum "$OUT_BASE/selv_input.jsonl"
} | tee -a "$LOG"

cd "$ROOT/.."
"$PY_B" "$REPO/scripts/gpu_lock.py" wait --who "rc6-corrected-scoreboard" \
  --wait-s 7200 --poll-s 5 -- \
  env WSB_ROCM_TORCH_OVERRIDE=1 python3 "$ROOT/wsb_eval.py" \
  score --input "$OUT_BASE/selv_input.jsonl" \
        --output "$OUT_BASE/selv_metrics" \
        --mode standard --metrics songbench,mulan,allmusiccaps >> "$LOG" 2>&1
rc=$?
echo "[rc6-selv] evaluator rc=$rc" | tee -a "$LOG"
exit $rc
