#!/usr/bin/env bash
# run_armB_campaign.sh — launch/resume the Arm B (SGLang ROCm) full WSB
# campaign, detached-safe, single-GPU (gpu_lock held for the WHOLE campaign:
# server + driver), resume-safe (reuses the existing run_id if the campaign
# dir already exists; run_wsb.py write-once identity enforces protocol).
#
# Lifecycle: acquire launcher flock -> no-op if driver already alive ->
# gpu_lock wait -> start server -> health poll -> identity receipt ->
# run_wsb.py driver (foreground of this script) -> ALWAYS stop server
# gracefully on exit (trap).
#
# P0 lifecycle fix: this script previously registered `trap stop_server EXIT`
# and then `exec`-replaced itself with gpu_lock.py — the exec DISCARDED the
# trap, so the inner bash orphaned the SGLang server on every driver exit
# path. The launcher now runs gpu_lock.py as a foreground CHILD (no exec),
# keeps EXIT/INT/TERM traps for the whole campaign, forwards signals to the
# gpu_lock child, and stops the server through the verified identity receipt
# only (never by name/port matching).
set -uo pipefail
WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUNS_DIR="${YUE2_RUNS:-/data/yue2-runs}/armB_wsb_full"
PY_B="$WS/environments/yue2-gfx1100/bin/python"
PORT="${ARMB_PORT:-31000}"
HOST="${ARMB_HOST:-127.0.0.1}"
URL="http://$HOST:$PORT"
# LOG_DIR is a DIRECTORY; never export LOG (dir) into serve_yue2_gfx1100.sh,
# which reads SERVER_LOG as a FILE (live boot-failure defect 2026-11-18).
LOG_DIR="${ARMB_LOG_DIR:-$WS/logs}"
SERVER_LOG_FILE="$LOG_DIR/server_yue2_gfx1100.log"
BOOT_LOG="$LOG_DIR/armB_server_boot.log"
RECEIPT_DIR="$LOG_DIR/armB_server_identity"
RECEIPT="$RECEIPT_DIR/server-identity.json"
HEALTH_TIMEOUT_S="${ARMB_HEALTH_TIMEOUT_S:-1800}"
HEALTH_POLL_S="${ARMB_HEALTH_POLL_S:-5}"

[ -x "$PY_B" ] || { echo "FATAL: Environment B python missing: $PY_B (build_envB.sh first)"; exit 2; }

mkdir -p "$LOG_DIR" "$WS/locks"
exec 9>>"$WS/locks/armB_launcher.lock"
if ! flock -n 9; then
  echo "[armB-launcher] another Arm B launcher holds the lock; exiting (no-op)"
  exit 0
fi

if "$PY_B" "$REPO/scripts/campaign_ops/driver_alive.py" --script run_wsb.py \
      --runs "$RUNS_DIR" >/dev/null 2>&1; then
  echo "[armB-launcher] Arm B driver already alive for $RUNS_DIR; exiting (no-op)"
  exit 0
fi

# resume-safe run id: reuse what the campaign dir already pinned
RUN_ID="armB_full_$(date -u +%Y%m%dT%H%M%SZ)"
if [ -f "$RUNS_DIR/run_config.json" ]; then
  RUN_ID=$("$PY_B" -c "import json;print(json.load(open('$RUNS_DIR/run_config.json'))['run_id'])")
  echo "[armB-launcher] resuming existing campaign run_id=$RUN_ID"
fi
echo "[armB-launcher] run_id=$RUN_ID runs=$RUNS_DIR"

STOP_FAILED=0
stop_server() {
  echo "[armB-launcher] graceful server stop (verified receipt only)"
  "$PY_B" "$REPO/scripts/server_identity.py" stop --receipt "$RECEIPT" \
    --timeout "${ARMB_STOP_TIMEOUT_S:-180}" \
    || { echo "[armB-launcher] WARNING: server stop returned $?"; STOP_FAILED=1; }
}

GATEWAY_PID=""
on_signal() {
  echo "[armB-launcher] signal $1 received: forwarding to gateway + stopping server"
  [ -n "$GATEWAY_PID" ] && kill "-$1" "$GATEWAY_PID" 2>/dev/null
  stop_server
  exit $((128 + $1))
}
on_exit() {
  local grc="${GATEWAY_RC:-$?}"
  stop_server
  # a verified server that could not be stopped (BLOCKED) must never hide
  # behind an exit 0 — the campaign result may be fine, the LIFECYCLE is not
  if [ "${STOP_FAILED:-0}" -ne 0 ] && [ "$grc" -eq 0 ]; then
    echo "[armB-launcher] FATAL: driver finished but the server survived graceful stop; escalating rc"
    grc=1
  fi
  exit "$grc"
}
trap on_exit EXIT
trap 'on_signal 2' INT
trap 'on_signal 15' TERM

campaign_flow() {
  echo "[armB-launcher] starting server"
  setsid nohup env YUE2_WORKSPACE="$WS" YUE2_VENV="$WS/environments/yue2-gfx1100" \
    PORT="$PORT" HOST="$HOST" SERVER_LOG="$SERVER_LOG_FILE" \
    bash "$REPO/scripts/serve_yue2_gfx1100.sh" \
    > "$BOOT_LOG" 2>&1 < /dev/null &

  local t0=$(date +%s) ok=0
  while [ $(( $(date +%s) - t0 )) -lt "$HEALTH_TIMEOUT_S" ]; do
    if curl -sf --max-time 5 "$URL/health" >/dev/null 2>&1; then ok=1; break; fi
    sleep "$HEALTH_POLL_S"
  done
  [ "$ok" -eq 1 ] || { echo "[armB-launcher] FATAL: server unhealthy after ${HEALTH_TIMEOUT_S}s (boot log: $BOOT_LOG)"; return 1; }
  echo "[armB-launcher] server healthy"

  "$PY_B" "$REPO/scripts/server_identity.py" capture \
    --run-state "$RECEIPT_DIR" --model "$WS/models/YuE2-3B" --host "$HOST" --port "$PORT" \
    || { echo "[armB-launcher] FATAL: identity capture failed"; return 1; }
  "$PY_B" "$REPO/scripts/server_identity.py" verify --receipt "$RECEIPT" \
    || { echo "[armB-launcher] FATAL: identity verify failed"; return 1; }

  echo "[armB-launcher] launching driver (run_wsb.py)"
  "$PY_B" "$REPO/scripts/run_wsb.py" \
    --runs "$RUNS_DIR" \
    --run-id "$RUN_ID" \
    --server "$URL" \
    >> "$LOG_DIR/armB_${RUN_ID}.log" 2>&1
}

export WS REPO RUNS_DIR PY_B PORT HOST URL LOG_DIR SERVER_LOG_FILE BOOT_LOG RECEIPT_DIR RECEIPT \
  RUN_ID HEALTH_TIMEOUT_S HEALTH_POLL_S
# no exec: the launcher OWNS the server lifecycle; its traps must survive.
# The gateway runs in the BACKGROUND so `wait` is interruptible — a foreground
# child would delay trap handling until it exits on its own.
"$PY_B" "$REPO/scripts/gpu_lock.py" \
  wait --who "armB-campaign:${RUN_ID}" --wait-s "${ARMB_GPU_LOCK_WAIT_S:-7200}" -- \
  bash -c "$(declare -f campaign_flow stop_server); campaign_flow" &
GATEWAY_PID=$!
wait "$GATEWAY_PID"
GATEWAY_RC=$?
GATEWAY_PID=""
exit "$GATEWAY_RC"
