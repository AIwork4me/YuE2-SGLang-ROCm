#!/usr/bin/env bash
# run_with_server.sh — repo-level server lifecycle wrapper (RC4.1 M3; closes
# RC4 follow-up R1-L1 "pilot driver exits without stopping its server").
#
# Full lifecycle, ALL under one continuous gpu_lock hold:
#   GPU_IDENTITY_VERIFY (fail-loud) → START SERVER → HEALTH → IDENTITY
#   CAPTURE+VERIFY → READINESS (scheduler-worker aware) → EXECUTE COMMAND
#   → VERIFIED STOP → CLEANUP CHECK (port free, process gone)
# Failure paths run the same cleanup. No orphan server survives this script.
#
# Design notes (same live-defect classes already fixed in
# run_armB_campaign.sh — kept consistent deliberately):
#   * NO exec into gpu_lock.py: exec discards this shell's traps; the
#     launcher OWNS the verified-stop cleanup.
#   * The gateway (gpu_lock + flow) runs in the BACKGROUND so `wait` is
#     interruptible; signals are forwarded AND followed by cleanup.
#   * The server is stopped ONLY through the verified identity receipt —
#     never by name/port match, never pkill.
#
# Usage:
#   bash scripts/campaign_ops/run_with_server.sh --log-dir D [--port 31000] \
#        [--health-timeout-s 1800] [--readiness-check 1] -- <command...>
#
# Exit: command's rc on success-path; 1 on any lifecycle failure; 128+sig on
# signals (after cleanup).
set -uo pipefail
WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PORT="${RWS_PORT:-31000}"
HOST="${RWS_HOST:-127.0.0.1}"
URL="http://$HOST:$PORT"
LOG_DIR="${RWS_LOG_DIR:-$WS/logs}"
WHO="${RWS_LOCK_WHO:-rc41-lifecycle-$(date -u +%Y%m%dT%H%M%SZ)}"
HEALTH_TIMEOUT_S="${RWS_HEALTH_TIMEOUT_S:-1800}"
HEALTH_POLL_S="${RWS_HEALTH_POLL_S:-5}"
GPU_LOCK_WAIT_S="${RWS_GPU_LOCK_WAIT_S:-7200}"
EXPECT_ARCH="${YUE2_EXPECT_GPU_ARCH:-gfx1100}"
PY_B="$WS/environments/yue2-gfx1100/bin/python"
[ -x "$PY_B" ] || PY_B="$(command -v python3)"
CMD=()
READINESS_CHECK=1

while [ $# -gt 0 ]; do
  case "$1" in
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --health-timeout-s) HEALTH_TIMEOUT_S="$2"; shift 2 ;;
    --readiness-check) READINESS_CHECK="$2"; shift 2 ;;
    --) shift; CMD=("$@"); break ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [ ${#CMD[@]} -eq 0 ]; then
  echo "usage: run_with_server.sh --log-dir D [--port N] -- <command...>" >&2
  exit 2
fi

SERVER_LOG_FILE="$LOG_DIR/server_yue2_gfx1100.log"
BOOT_LOG="$LOG_DIR/rws_server_boot.log"
RECEIPT_DIR="$LOG_DIR/rws_server_identity"
RECEIPT="$RECEIPT_DIR/server-identity.json"
IDENTITY_DIR="$LOG_DIR/rws_gpu_identity"
INNER_PID_FILE="$LOG_DIR/rws_inner.pid"
mkdir -p "$LOG_DIR" "$RECEIPT_DIR" "$IDENTITY_DIR"

GATEWAY_PID=""
STOP_FAILED=0

stop_server() {
  if [ ! -f "$RECEIPT" ]; then
    return 0
  fi
  echo "[rws] verified server stop (receipt: $RECEIPT)"
  "$PY_B" "$REPO/scripts/server_identity.py" stop \
    --receipt "$RECEIPT" --timeout "${RWS_STOP_TIMEOUT_S:-180}"
  local rc=$?
  # rc 0 = stopped now; rc 2 = verify-failed (already gone) — both fine.
  # anything else (3 ambiguous / 4 refused / 5 blocked-alive / 6 busy) is a
  # lifecycle failure: a server we cannot account for must not hide.
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
    echo "[rws] FAIL: verified stop returned rc=$rc" >&2
    STOP_FAILED=1
  fi
}

check_port_freed() {
  "$PY_B" -c "
import socket, sys
s = socket.socket()
try:
    s.connect(('127.0.0.1', int(sys.argv[1])))
except OSError:
    sys.exit(0)  # connection refused: nothing listening, port free
sys.exit(1)  # something answered on the port after a verified stop
" "$PORT" || { echo "[rws] FAIL: port $PORT still occupied after stop" >&2
                return 1; }
}

on_signal() {
  local sig=$1 rc=$((128 + $1))
  echo "[rws] signal $sig: forwarding to gateway + inner flow, then cleanup" >&2
  [ -n "$GATEWAY_PID" ] && kill "-$sig" "$GATEWAY_PID" 2>/dev/null
  # cascade into the inner flow (pid file) so the wrapped COMMAND receives
  # the signal too — an orphaned command must not keep generating unaware
  if [ -f "$INNER_PID_FILE" ]; then
    local ipid
    ipid=$(cat "$INNER_PID_FILE" 2>/dev/null || true)
    [ -n "$ipid" ] && kill "-$sig" "$ipid" 2>/dev/null
  fi
  wait "$GATEWAY_PID" 2>/dev/null
  GATEWAY_PID=""
  stop_server
  exit "$rc"
}
trap 'on_signal 2' INT
trap 'on_signal 15' TERM
on_exit() {
  local grc="${GATEWAY_RC:-$?}"
  stop_server
  if [ "${STOP_FAILED:-0}" -eq 0 ] && [ "$grc" -eq 0 ]; then
    check_port_freed || { STOP_FAILED=1; grc=1; }
  fi
  if [ "${STOP_FAILED:-0}" -ne 0 ] && [ "$grc" -eq 0 ]; then
    echo "[rws] FATAL: flow finished but the lifecycle did not close cleanly" >&2
    grc=1
  fi
  exit "$grc"
}
trap on_exit EXIT

lifecycle_flow() {
  FLOW_RC=0
  echo $$ > "$INNER_PID_FILE"

  echo "[rws] 1/7 GPU identity (fail-loud, expected arch=$EXPECT_ARCH)"
  if ! "$PY_B" "$REPO/scripts/gpu_identity.py" verify \
      --expect-arch "$EXPECT_ARCH" \
      --receipt "$IDENTITY_DIR/pre_boot_gpu_identity.json"; then
    echo "[rws] FAIL: GPU identity not verified — refusing to start server" >&2
    return 1
  fi

  echo "[rws] 2/7 starting server (serve_yue2_gfx1100.sh)"
  setsid nohup env YUE2_WORKSPACE="$WS" YUE2_VENV="$WS/environments/yue2-gfx1100" \
    PORT="$PORT" HOST="$HOST" SERVER_LOG="$SERVER_LOG_FILE" \
    bash "$REPO/scripts/serve_yue2_gfx1100.sh" \
    > "$BOOT_LOG" 2>&1 < /dev/null &

  echo "[rws] 3/7 polling $URL/health (bounded ${HEALTH_TIMEOUT_S}s)"
  local t0=$(date +%s) ok=0
  while [ $(( $(date +%s) - t0 )) -lt "$HEALTH_TIMEOUT_S" ]; do
    if curl -sf --max-time 5 "$URL/health" >/dev/null 2>&1; then ok=1; break; fi
    sleep "$HEALTH_POLL_S"
  done
  if [ "$ok" -ne 1 ]; then
    echo "[rws] FAIL: no health in ${HEALTH_TIMEOUT_S}s (boot: $BOOT_LOG)" >&2
    return 1
  fi

  echo "[rws] 4/7 identity capture + verify"
  if ! "$PY_B" "$REPO/scripts/server_identity.py" capture \
      --run-state "$RECEIPT_DIR" --model "$WS/models/YuE2-3B" \
      --host "$HOST" --port "$PORT"; then
    echo "[rws] FAIL: identity capture" >&2
    return 1
  fi
  if ! "$PY_B" "$REPO/scripts/server_identity.py" verify --receipt "$RECEIPT"; then
    echo "[rws] FAIL: identity verify" >&2
    return 1
  fi

  if [ "$READINESS_CHECK" = "1" ]; then
    echo "[rws] 5/7 readiness (scheduler-worker aware; HTTP 200 alone is NOT READY)"
    if ! "$PY_B" "$REPO/scripts/server_readiness.py" check \
        --receipt "$RECEIPT" --url "$URL"; then
      echo "[rws] FAIL: server not GENERATION_READY" >&2
      return 1
    fi
  else
    echo "[rws] 5/7 readiness check skipped (--readiness-check 0)"
  fi

  echo "[rws] 6/7 executing:$CMD_STR"
  eval "CMD=($CMD_STR)"
  "${CMD[@]}" &
  local cmd_pid=$!
  trap 'kill -TERM "$cmd_pid" 2>/dev/null' TERM INT
  local cmd_rc=0
  wait "$cmd_pid" || cmd_rc=$?
  trap - TERM INT
  echo "[rws] command rc=$cmd_rc"
  return "$cmd_rc"
}

# command safely re-quoted for the inner bash (%q applied exactly once, here)
CMD_STR=""
for c in "${CMD[@]}"; do CMD_STR+=" $(printf '%q' "$c")"; done
export WS REPO PORT HOST URL LOG_DIR SERVER_LOG_FILE BOOT_LOG RECEIPT_DIR \
  RECEIPT IDENTITY_DIR HEALTH_TIMEOUT_S EXPECT_ARCH CMD_STR READINESS_CHECK \
  PY_B INNER_PID_FILE

"$PY_B" "$REPO/scripts/gpu_lock.py" wait --who "$WHO" \
  --wait-s "$GPU_LOCK_WAIT_S" -- \
  bash -c "$(declare -f lifecycle_flow); lifecycle_flow" &
GATEWAY_PID=$!
wait "$GATEWAY_PID"
GATEWAY_RC=$?
GATEWAY_PID=""
exit "$GATEWAY_RC"
