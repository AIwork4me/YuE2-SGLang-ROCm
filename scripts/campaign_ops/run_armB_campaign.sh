#!/usr/bin/env bash
# run_armB_campaign.sh — launch/resume the Arm B (SGLang ROCm) full WSB
# campaign, detached-safe, single-GPU, resume-safe (reuses the existing run_id
# if the campaign dir already exists; run_wsb.py write-once identity enforces
# protocol).
#
# RC5 M1.1 (P0, GPU Lock Lifecycle Atomicity): the lock + the whole server
# lifecycle now live in ONE supervisor process (scripts/gpu_lifecycle.py),
# which cleans up BEFORE the flock is released. The RC4.1 layout ran
# gpu_lock.py as a background gateway: the gateway released the lock when the
# inner flow returned and only THEN did this shell's EXIT trap stop the
# server — a window in which a second job could take the GPU while the first
# server still held VRAM. (RC4.1 had already fixed the older `exec` defect
# that orphaned the server entirely.)
#
# Lifecycle: launcher flock → no-op if driver already alive → gpu identity →
# GPU idle → start server → health → identity receipt → readiness → run_wsb.py
# driver → drain → verified stop → tree/port/GPU release verified → unlock.
set -uo pipefail

WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUNS_DIR="${YUE2_RUNS:-/data/yue2-runs}/armB_wsb_full"
VENV="${YUE2_VENV:-$WS/environments/yue2-gfx1100}"
PY_B="$VENV/bin/python"
PORT="${ARMB_PORT:-31000}"
HOST="${ARMB_HOST:-127.0.0.1}"
URL="http://$HOST:$PORT"
# LOG_DIR is a DIRECTORY; never export LOG (dir) into serve_yue2_gfx1100.sh,
# which reads SERVER_LOG as a FILE (live boot-failure defect 2026-11-18).
LOG_DIR="${ARMB_LOG_DIR:-$WS/logs}"
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

DRIVER_LOG="$LOG_DIR/armB_${RUN_ID}.log"
SUP=(
  --who "armB-campaign:${RUN_ID}"
  --workspace "$WS"
  --venv "$VENV"
  --host "$HOST"
  --port "$PORT"
  --log-dir "$LOG_DIR"
  --serve-script "$REPO/scripts/serve_yue2_gfx1100.sh"
  --model "${MODEL_PATH:-$WS/models/YuE2-3B}"
  --vae "${VAE_PATH:-$WS/models/YuE2-Vae-legacy}"
  --expect-arch "${YUE2_EXPECT_GPU_ARCH:-gfx1100}"
  --health-timeout-s "$HEALTH_TIMEOUT_S"
  --health-poll-s "$HEALTH_POLL_S"
  --readiness-check 1
  --wait-s "${ARMB_GPU_LOCK_WAIT_S:-7200}"
  --poll-s 2
  --receipt-dir "$LOG_DIR/armB_server_identity"
  --identity-dir "$LOG_DIR/armB_gpu_identity"
  --boot-log "$LOG_DIR/armB_server_boot.log"
  --server-log "$LOG_DIR/server_yue2_gfx1100.log"
  --drain-s "${ARMB_DRAIN_S:-600}"
  --cmd-drain-s "${ARMB_CMD_DRAIN_S:-1800}"
  --port-release-timeout-s "${ARMB_PORT_RELEASE_TIMEOUT_S:-60}"
  --gpu-release-timeout-s "${ARMB_GPU_RELEASE_TIMEOUT_S:-180}")
[ -n "${YUE2_GPU_LOCK:-}" ] && SUP+=(--lock "$YUE2_GPU_LOCK")
[ -n "${YUE2_EXPECT_GPU_BDF:-}" ] && SUP+=(--expect-bdf "$YUE2_EXPECT_GPU_BDF")
[ -n "${ARMB_STOP_TIMEOUT_S:-}" ] && SUP+=(--stop-timeout-s "$ARMB_STOP_TIMEOUT_S")

# The supervisor is the ONLY lock holder and owns the cleanup, so this shell
# execs into it (no background gateway, no trap that runs after the unlock).
# The driver keeps its historical log file via an exec-ing `bash -c` (same pid,
# so signals forwarded by the supervisor reach the driver itself).
exec "$PY_B" "$REPO/scripts/gpu_lifecycle.py" "${SUP[@]}" -- \
  bash -c 'exec "$@" >> "$0" 2>&1' "$DRIVER_LOG" \
  "$PY_B" "$REPO/scripts/run_wsb.py" \
    --runs "$RUNS_DIR" \
    --run-id "$RUN_ID" \
    --server "$URL"
