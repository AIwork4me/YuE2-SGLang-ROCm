#!/usr/bin/env bash
# run_omni_scoring.sh - arm-B (SGLang-Omni) WSB official scoring pipeline.
# Mirrors the reviewed v2 state machine (audit -> stop generation server ->
# PER+SongBench -> MuLan+AllMusicCaps) with the Omni server port 32100.
# Scoring itself is the frozen official evaluator, byte-identical invocation.
set -uo pipefail

WS=/workspace/yue2-sglang-rocm-w7900
BENCH=/workspace/yue2-omni-pr/bench
RUN_ID=${1:-$(cat "$BENCH/.full_run_id")}
RUNS="$BENCH/runs/$RUN_ID"
LOG="$BENCH/logs/scoring_$RUN_ID.log"
STATE_DIR="$RUNS/run-state"
METRICS_PY="$WS/benchmark/wsb_metrics/.venvs/metrics/bin/python"
OMNI_PORT=32100

log() { echo "[$(date -u +%FT%TZ)] [omni-score] $*" | tee -a "$LOG"; }
mkdir -p "$STATE_DIR"

# ---- 1) strict audit: 384/384 -------------------------------------------------
log "strict audit of $RUNS"
if ! AUDIT=$( "$METRICS_PY" "$WS/evidence-repo/scripts/verify_wsb_artifacts.py" \
    --runs "$RUNS" --mode full 2>&1 | tee -a "$LOG" ); then
  log "audit FAILED"; exit 2
fi
echo "$AUDIT" > "$RUNS/audit.json"
if ! python3 -c "import json,sys; d=json.load(open('$RUNS/audit.json')); sys.exit(0 if d['verdict']=='FULL' and d['problem_count']==0 else 1)"; then
  log "audit verdict not FULL - refusing to score"; exit 2
fi
log "audit verdict FULL (384/384)"

# ---- 2) stop the Omni generation server (exact-PID, verified) -----------------
SRV_PID=$(pgrep -f "sgl-omni serve" | head -1 || true)
if [ -n "${SRV_PID:-}" ] && [ -d "/proc/$SRV_PID" ] && \
   ! grep -q "state:.*Z" "/proc/$SRV_PID/status" 2>/dev/null; then
  if tr '\0' ' ' < "/proc/$SRV_PID/cmdline" 2>/dev/null | grep -qa -- "--port $OMNI_PORT"; then
    log "stopping omni server pid $SRV_PID (SIGINT)"
    kill -INT "$SRV_PID"
    for i in $(seq 1 60); do
      [ -d "/proc/$SRV_PID" ] || break
      grep -q "state:.*Z" "/proc/$SRV_PID/status" 2>/dev/null && break
      sleep 5
    done
  else
    log "pid $SRV_PID does not own port $OMNI_PORT - not stopping"
  fi
else
  log "no live omni server - nothing to stop"
fi
sleep 10

# ---- 3) PER + SongBench (unselected 384) --------------------------------------
cd "$WS/benchmark/wsb_metrics"
log "scoring per,songbench (standard mode)"
if ! WSB_ROCM_TORCH_OVERRIDE=1 YUE2_WORKSPACE="$WS" HF_HOME="$WS/.cache/huggingface" \
     "$METRICS_PY" wsb_eval.py score \
       --input "$RUNS/evaluation_inputs.jsonl" \
       --output "$RUNS/scores" --mode standard --metrics per,songbench >> "$LOG" 2>&1; then
  log "PER/SongBench scoring FAILED - see log"; exit 3
fi
log "PER+SongBench complete"

# ---- 4) MuLan + AllMusicCaps (SAME official PER best-of-2 selection) ----------
log "scoring mulan,allmusiccaps (selected 192)"
if ! WSB_ROCM_TORCH_OVERRIDE=1 YUE2_WORKSPACE="$WS" HF_HOME="$WS/.cache/huggingface" \
     "$METRICS_PY" wsb_eval.py score \
       --input "$RUNS/evaluation_inputs.jsonl" \
       --per-results "$RUNS/scores/per_song.jsonl" \
       --output "$RUNS/additional" --metrics mulan,allmusiccaps >> "$LOG" 2>&1; then
  log "mulan/allmusiccaps scoring FAILED - see log"; exit 4
fi
log "MuLan+AllMusicCaps complete"
log "PIPELINE COMPLETE (scoring stages succeeded)"
