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
#   6. REAL music generation: one bounded full-pipeline request via
#      armb_acceptance_request.py; audio must decode, be non-silent and
#      >= 5 s — /health + /v1/models alone prove nothing about generation
#   7. graceful stop via server_identity.py stop (SIGINT -> SIGTERM, never
#      SIGKILL); a server that will not stop = FAILED acceptance
#
# The server is stopped on EVERY exit path: the inner flow registers EXIT /
# INT / TERM traps itself (the outer script must not `exec` past its traps —
# live defect class found in run_armB_campaign.sh), and stop only ever
# targets the verified identity receipt, never a name/port match.
#
# Exit 0 only when every step passes.
set -uo pipefail
WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PORT="${ARMB_PORT:-31000}"
HOST="${ARMB_HOST:-127.0.0.1}"
URL="http://$HOST:$PORT"
# LOG_DIR is a DIRECTORY (receipts, boot logs). Never export LOG: the serve
# script historically read LOG as a FILE and died when it received this
# directory (live defect, 2026-11-18T23:55Z attempt).
LOG_DIR="${ARMB_LOG_DIR:-$WS/logs}"
SERVER_LOG_FILE="$LOG_DIR/server_yue2_gfx1100.log"
BOOT_LOG="$LOG_DIR/armB_server_boot.log"
RECEIPT_DIR="$LOG_DIR/armB_server_identity"
RECEIPT="$RECEIPT_DIR/server-identity.json"
ACC_DIR="$LOG_DIR/armB_acceptance"
HEALTH_TIMEOUT_S="${ARMB_HEALTH_TIMEOUT_S:-1800}"
HEALTH_POLL_S="${ARMB_HEALTH_POLL_S:-5}"
GEN_TIMEOUT_S="${ARMB_GEN_TIMEOUT_S:-1800}"
PY_B="$WS/environments/yue2-gfx1100/bin/python"

acceptance_flow() {
  local rc=0
  FLOW_RC=0
  # stop the server via the VERIFIED identity receipt on every exit path;
  # a stop failure is itself an acceptance failure (server must not survive)
  finish() {
    echo "[armB-acceptance] finish: graceful server stop (flow rc=${FLOW_RC:-0})"
    if ! "$WS/environments/yue2-gfx1100/bin/python" \
        "$REPO/scripts/server_identity.py" stop --receipt "$RECEIPT" \
        --timeout "${ARMB_STOP_TIMEOUT_S:-180}"; then
      echo "[armB-acceptance] FAIL: server did not stop gracefully"
      FLOW_RC=1
    fi
    # after a successful stop the receipt must no longer verify as live
    if "$WS/environments/yue2-gfx1100/bin/python" \
        "$REPO/scripts/server_identity.py" verify --receipt "$RECEIPT" \
        >/dev/null 2>&1; then
      echo "[armB-acceptance] FAIL: server still verifiable after stop"
      FLOW_RC=1
    fi
  }
  on_signal() {
    FLOW_RC=$((128 + $1))
    finish
    trap - EXIT INT TERM
    exit "$FLOW_RC"
  }
  trap 'on_signal 2' INT
  trap 'on_signal 15' TERM
  trap 'finish; trap - EXIT INT TERM; exit "${FLOW_RC:-0}"' EXIT

  echo "[armB-acceptance] starting server (serve_yue2_gfx1100.sh)"
  # server boot output goes to a FILE, never /dev/null — a server that dies
  # during boot must leave evidence (the 22:55Z attempt died silently)
  setsid nohup env YUE2_WORKSPACE="$WS" YUE2_VENV="$WS/environments/yue2-gfx1100" \
    PORT="$PORT" HOST="$HOST" SERVER_LOG="$SERVER_LOG_FILE" \
    bash "$REPO/scripts/serve_yue2_gfx1100.sh" \
    > "$BOOT_LOG" 2>&1 < /dev/null &

  echo "[armB-acceptance] polling $URL/health (bounded ${HEALTH_TIMEOUT_S}s)"
  local t0=$(date +%s) ok=0
  while [ $(( $(date +%s) - t0 )) -lt "$HEALTH_TIMEOUT_S" ]; do
    if curl -sf --max-time 5 "$URL/health" >/dev/null 2>&1; then ok=1; break; fi
    sleep "$HEALTH_POLL_S"
  done
  if [ "$ok" -ne 1 ]; then
    echo "[armB-acceptance] FAIL: server did not become healthy in ${HEALTH_TIMEOUT_S}s (boot log: $BOOT_LOG; server log: $SERVER_LOG_FILE)"
    FLOW_RC=1; return "$FLOW_RC"
  fi
  echo "[armB-acceptance] server healthy"

  "$WS/environments/yue2-gfx1100/bin/python" "$REPO/scripts/server_identity.py" \
    capture --run-state "$RECEIPT_DIR" --model "$WS/models/YuE2-3B" --host "$HOST" --port "$PORT" \
    || { echo "[armB-acceptance] FAIL: identity capture"; FLOW_RC=1; return 1; }
  "$WS/environments/yue2-gfx1100/bin/python" "$REPO/scripts/server_identity.py" \
    verify --receipt "$RECEIPT" \
    || { echo "[armB-acceptance] FAIL: identity verify"; FLOW_RC=1; return 1; }

  local models
  models=$(curl -sf --max-time 15 "$URL/v1/models" 2>/dev/null || echo "")
  if [ -z "$models" ] || ! echo "$models" | grep -q "YuE2\|yue2"; then
    echo "[armB-acceptance] FAIL: /v1/models does not advertise the YuE2 model: ${models:0:200}"
    FLOW_RC=1; return 1
  fi
  echo "[armB-acceptance] /v1/models advertises the pinned YuE2 model"

  echo "[armB-acceptance] REAL music-generation acceptance (bounded ${GEN_TIMEOUT_S}s)"
  if ! "$WS/environments/yue2-gfx1100/bin/python" \
      "$REPO/scripts/campaign_ops/armb_acceptance_request.py" \
      --server "$URL" --out-dir "$ACC_DIR" --timeout "$GEN_TIMEOUT_S"; then
    echo "[armB-acceptance] FAIL: music-generation acceptance (receipt dir: $ACC_DIR)"
    FLOW_RC=1; return 1
  fi
  echo "[armB-acceptance] music-generation acceptance PASS (receipt: $ACC_DIR/acceptance_receipt.json)"

  finish
  trap - EXIT INT TERM
  rc="${FLOW_RC:-0}"
  if [ "$rc" -eq 0 ]; then
    echo "ARMB_ACCEPTANCE_PASS"
  fi
  return "$rc"
}

mkdir -p "$LOG_DIR"
# export (not command-prefix assignment): acceptance_flow reads $WS/$REPO/...
# directly — the 22:55Z attempt died instantly because WS was empty in the
# bash -c environment and serve_yue2_gfx1100.sh fell back to the repo root
# (no environments/ there -> source activate failed under set -e).
export WS REPO PORT HOST URL LOG_DIR SERVER_LOG_FILE BOOT_LOG RECEIPT_DIR RECEIPT ACC_DIR \
  HEALTH_TIMEOUT_S HEALTH_POLL_S GEN_TIMEOUT_S
exec "$PY_B" "$REPO/scripts/gpu_lock.py" \
  wait --who armB-acceptance --wait-s "${ARMB_GPU_LOCK_WAIT_S:-7200}" -- \
  bash -c "$(declare -f acceptance_flow); acceptance_flow"
