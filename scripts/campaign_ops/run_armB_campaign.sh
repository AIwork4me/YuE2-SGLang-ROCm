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
set -uo pipefail
WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUNS_DIR="${YUE2_RUNS:-/data/yue2-runs}/armB_wsb_full"
PY_B="$WS/environments/yue2-gfx1100/bin/python"
PORT="${ARMB_PORT:-31000}"
HOST="${ARMB_HOST:-127.0.0.1}"
URL="http://$HOST:$PORT"
LOG="$WS/logs"
RECEIPT="$LOG/armB_server_identity/server-identity.json"
HEALTH_TIMEOUT_S="${ARMB_HEALTH_TIMEOUT_S:-1800}"

[ -x "$PY_B" ] || { echo "FATAL: Environment B python missing: $PY_B (build_envB.sh first)"; exit 2; }

mkdir -p "$LOG" "$WS/locks"
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

stop_server() {
  echo "[armB-launcher] graceful server stop"
  "$PY_B" "$REPO/scripts/server_identity.py" stop --receipt "$RECEIPT" --timeout 180 \
    || echo "[armB-launcher] WARNING: server stop returned $?"
}
trap stop_server EXIT

campaign_flow() {
  echo "[armB-launcher] starting server"
  setsid nohup env YUE2_WORKSPACE="$WS" YUE2_VENV="$WS/environments/yue2-gfx1100" \
    PORT="$PORT" HOST="$HOST" \
    bash "$REPO/scripts/serve_yue2_gfx1100.sh" \
    > "$LOG/armB_server_boot.log" 2>&1 < /dev/null &

  local t0=$(date +%s) ok=0
  while [ $(( $(date +%s) - t0 )) -lt "$HEALTH_TIMEOUT_S" ]; do
    if curl -sf --max-time 5 "$URL/health" >/dev/null 2>&1; then ok=1; break; fi
    sleep 10
  done
  [ "$ok" -eq 1 ] || { echo "[armB-launcher] FATAL: server unhealthy after ${HEALTH_TIMEOUT_S}s"; return 1; }
  echo "[armB-launcher] server healthy"

  "$PY_B" "$REPO/scripts/server_identity.py" capture \
    --run-state "$RECEIPT" --model "$WS/models/YuE2-3B" --host "$HOST" --port "$PORT" \
    || { echo "[armB-launcher] FATAL: identity capture failed"; return 1; }
  "$PY_B" "$REPO/scripts/server_identity.py" verify --receipt "$RECEIPT" \
    || { echo "[armB-launcher] FATAL: identity verify failed"; return 1; }

  echo "[armB-launcher] launching driver (run_wsb.py)"
  "$PY_B" "$REPO/scripts/run_wsb.py" \
    --runs "$RUNS_DIR" \
    --run-id "$RUN_ID" \
    --server "$URL" \
    >> "$LOG/armB_${RUN_ID}.log" 2>&1
}

export WS REPO RUNS_DIR PY_B PORT HOST URL LOG RECEIPT HEALTH_TIMEOUT_S
exec "$PY_B" "$REPO/scripts/gpu_lock.py" \
  wait --who "armB-campaign:${RUN_ID}" --wait-s "${ARMB_GPU_LOCK_WAIT_S:-7200}" -- \
  bash -c "$(declare -f campaign_flow stop_server); campaign_flow"
