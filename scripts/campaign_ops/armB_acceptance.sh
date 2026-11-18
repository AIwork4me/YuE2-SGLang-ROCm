#!/usr/bin/env bash
# armB_acceptance.sh — REAL Arm B server acceptance (Phase H gate).
#
# The mission_chain armB_acceptance stage runs this script (or the Owner sets
# YUE2_ARMB_ACCEPTANCE_CMD). It performs an actual serving acceptance on the
# physical GPU — no state file can substitute for a pass here:
#
#   1. GPU exclusivity: whole flow under scripts/gpu_lock.py (bounded wait,
#      never preempts a live holder)
#   2. torch stack assert + frozen flag matrix via serve_yue2_gfx1100.sh
#   3. bounded health poll of the SGLang endpoint (model load takes minutes)
#   4. server identity receipt via server_identity.py capture + verify
#      (PID liveness, argv, endpoint ownership — never pkill)
#   5. /v1/models must advertise the pinned model
#   6. graceful stop via server_identity.py stop (SIGINT -> SIGTERM, never
#      SIGKILL); a server that will not stop = FAILED acceptance
#
# Exit 0 only when every step passes.
set -uo pipefail
WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PORT="${ARMB_PORT:-31000}"
HOST="${ARMB_HOST:-127.0.0.1}"
URL="http://$HOST:$PORT"
LOG="$WS/logs"
RECEIPT="$LOG/armB_server_identity/server-identity.json"
HEALTH_TIMEOUT_S="${ARMB_HEALTH_TIMEOUT_S:-1800}"
PY_B="$WS/environments/yue2-gfx1100/bin/python"

acceptance_flow() {
  local rc=0
  echo "[armB-acceptance] starting server (serve_yue2_gfx1100.sh)"
  # server boot output goes to a FILE, never /dev/null — a server that dies
  # during boot must leave evidence (the 22:55Z attempt died silently)
  setsid nohup env YUE2_WORKSPACE="$WS" YUE2_VENV="$WS/environments/yue2-gfx1100" \
    PORT="$PORT" HOST="$HOST" \
    bash "$REPO/scripts/serve_yue2_gfx1100.sh" \
    > "$LOG/armB_server_boot.log" 2>&1 < /dev/null &

  echo "[armB-acceptance] polling $URL/health (bounded ${HEALTH_TIMEOUT_S}s)"
  local t0=$(date +%s) ok=0
  while [ $(( $(date +%s) - t0 )) -lt "$HEALTH_TIMEOUT_S" ]; do
    if curl -sf --max-time 5 "$URL/health" >/dev/null 2>&1; then ok=1; break; fi
    sleep 10
  done
  if [ "$ok" -ne 1 ]; then
    echo "[armB-acceptance] FAIL: server did not become healthy in ${HEALTH_TIMEOUT_S}s (log: $LOG/server_yue2_gfx1100.log)"
    "$WS/environments/yue2-gfx1100/bin/python" "$REPO/scripts/server_identity.py" stop --receipt "$RECEIPT" 2>/dev/null || true
    return 1
  fi
  echo "[armB-acceptance] server healthy"

  "$WS/environments/yue2-gfx1100/bin/python" "$REPO/scripts/server_identity.py" \
    capture --run-state "$RECEIPT" --model "$WS/models/YuE2-3B" --host "$HOST" --port "$PORT" \
    || { echo "[armB-acceptance] FAIL: identity capture"; rc=1; }
  if [ "$rc" -eq 0 ]; then
    "$WS/environments/yue2-gfx1100/bin/python" "$REPO/scripts/server_identity.py" \
      verify --receipt "$RECEIPT" || { echo "[armB-acceptance] FAIL: identity verify"; rc=1; }
  fi
  if [ "$rc" -eq 0 ]; then
    local models
    models=$(curl -sf --max-time 15 "$URL/v1/models" 2>/dev/null || echo "")
    if [ -z "$models" ] || ! echo "$models" | grep -q "YuE2\|yue2"; then
      echo "[armB-acceptance] FAIL: /v1/models does not advertise the YuE2 model: ${models:0:200}"
      rc=1
    else
      echo "[armB-acceptance] /v1/models advertises the pinned YuE2 model"
    fi
  fi

  echo "[armB-acceptance] graceful stop"
  if ! "$WS/environments/yue2-gfx1100/bin/python" "$REPO/scripts/server_identity.py" \
      stop --receipt "$RECEIPT" --timeout 180; then
    echo "[armB-acceptance] FAIL: server did not stop gracefully"
    rc=1
  fi

  if [ "$rc" -eq 0 ]; then
    echo "ARMB_ACCEPTANCE_PASS"
  fi
  return "$rc"
}

mkdir -p "$LOG"
# export (not command-prefix assignment): acceptance_flow reads $WS/$REPO/...
# directly — the 22:55Z attempt died instantly because WS was empty in the
# bash -c environment and serve_yue2_gfx1100.sh fell back to the repo root
# (no environments/ there -> source activate failed under set -e).
export WS REPO PORT HOST URL LOG RECEIPT HEALTH_TIMEOUT_S
exec "$PY_B" "$REPO/scripts/gpu_lock.py" \
  wait --who armB-acceptance --wait-s "${ARMB_GPU_LOCK_WAIT_S:-7200}" -- \
  bash -c "$(declare -f acceptance_flow); acceptance_flow"
