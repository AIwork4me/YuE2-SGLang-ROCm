#!/usr/bin/env bash
# rc5_supervise.sh — crash-resilient relauncher for ONE RC5 run.
#
# Repeats rc5_run.sh sessions until generation_summary.json reports
# complete == expected. Each session owns the GPU lock and the server, and
# cleans up before releasing it; the next session resumes (verified candidates
# are never regenerated). Stops on:
#   * completion                         -> exit 0
#   * a BLOCKED lifecycle marker         -> exit 3 (operator must intervene)
#   * two sessions in a row with no progress -> exit 4 (root-cause, don't loop)
#   * SIGINT / SIGTERM                   -> forwarded, exit 128+sig
# It never pushes, commits, merges or touches git configuration.
#
# Run it detached (tmux or setsid nohup) and attach a log:
#   tmux new-session -d -s rc5gen "bash scripts/campaign_ops/rc5_supervise.sh \
#       /data/yue2-runs/<run>/wsb_full <run_id> 2>&1 | tee -a /data/yue2-runs/<run>/supervisor.log"
set -uo pipefail

REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WS="${YUE2_WORKSPACE:-/data/yue2}"
RUN_DIR="$1"
RUN_ID="$2"
shift 2
IDX=("$@")
MAX_RELAUNCH="${RC5_MAX_RELAUNCH:-60}"
SLEEP_S="${RC5_RELAUNCH_SLEEP:-20}"
[ -n "$RUN_DIR" ] && [ -n "$RUN_ID" ] || {
  echo "usage: rc5_supervise.sh <run_dir> <run_id> [prompt_index ...]" >&2; exit 2; }
mkdir -p "$RUN_DIR"

# one supervisor per run
exec 8>"$RUN_DIR/.supervisor.lock"
if ! flock -n 8; then
  echo "[rc5-supervise] another supervisor already owns $RUN_DIR; exiting (no-op)"
  exit 0
fi

LOCK_FILE="${YUE2_GPU_LOCK:-$WS/gpu.lock}"
PY_B="${YUE2_VENV:-$WS/environments/yue2-gfx1100}/bin/python"
[ -x "$PY_B" ] || PY_B="$(command -v python3)"

complete_count() {
  "$PY_B" - "$RUN_DIR/generation_summary.json" <<'PY'
import json, sys
try:
    s = json.load(open(sys.argv[1]))
except Exception:
    print("-1 -1"); raise SystemExit
print(s.get("complete", -1), s.get("expected", -1))
PY
}

CHILD=""
on_signal() {
  echo "[rc5-supervise] signal $1: forwarding to the session, then exiting"
  [ -n "$CHILD" ] && kill -"$1" "$CHILD" 2>/dev/null
  wait "$CHILD" 2>/dev/null
  exit $((128 + $1))
}
trap 'on_signal 2' INT
trap 'on_signal 15' TERM

last_done=""
no_progress=0
for n in $(seq 1 "$MAX_RELAUNCH"); do
  read -r done expected <<<"$(complete_count)"
  if [ "$done" = "$expected" ] && [ "$done" -gt 0 ] 2>/dev/null; then
    echo "[rc5-supervise] COMPLETE: $done/$expected after $((n - 1)) session(s)"
    exit 0
  fi
  if [ -f "${LOCK_FILE}.BLOCKED" ]; then
    echo "[rc5-supervise] BLOCKED lifecycle marker present (${LOCK_FILE}.BLOCKED):"
    echo "               not starting another session. Resolve the recorded processes,"
    echo "               then: python scripts/gpu_lock.py unblock --yes"
    exit 3
  fi
  echo "[rc5-supervise] session $n starts (complete=$done expected=$expected) $(date -u +%FT%TZ)"
  bash "$REPO/scripts/campaign_ops/rc5_run.sh" "$RUN_DIR" "$RUN_ID" ${IDX[@]+"${IDX[@]}"} &
  CHILD=$!
  wait "$CHILD"
  rc=$?
  CHILD=""
  echo "[rc5-supervise] session $n exited rc=$rc $(date -u +%FT%TZ)"
  case "$rc" in
    130|143) exit "$rc" ;;
  esac
  read -r done expected <<<"$(complete_count)"
  if [ "$done" = "$last_done" ]; then
    no_progress=$((no_progress + 1))
  else
    no_progress=0
  fi
  last_done="$done"
  if [ "$no_progress" -ge 2 ]; then
    echo "[rc5-supervise] NO PROGRESS across three sessions (complete=$done): stopping" \
         "for root-cause analysis instead of looping (see $RUN_DIR/lifecycle/*/)"
    exit 4
  fi
  sleep "$SLEEP_S"
done
echo "[rc5-supervise] MAX_RELAUNCH ($MAX_RELAUNCH) reached without completion"
exit 5
