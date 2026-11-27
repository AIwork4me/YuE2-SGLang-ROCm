#!/usr/bin/env bash
# run_with_server.sh — repo-level server lifecycle wrapper (RC4.1 M3 → RC5 M1.1).
#
# RC5 P0 FIX (GPU Lock Lifecycle Atomicity). The RC4.1 layout ran the lock in a
# BACKGROUND gateway (gpu_lock.py) and stopped the server in the OUTER EXIT
# trap: the gateway released the flock when the inner flow returned, and only
# then did the outer shell run stop_server(). A second job could take the GPU
# lock while the first server still held VRAM.
#
# The whole lifecycle now lives in ONE process — scripts/gpu_lifecycle.py —
# which owns the flock fd for its entire life and performs the cleanup itself
# BEFORE the lock is released:
#
#   ACQUIRE LOCK → GPU IDENTITY (fail-loud, physical binding) → GPU IDLE
#   → LAUNCH OWNED SERVER (spawn receipt) → HEALTH → IDENTITY CAPTURE+VERIFY
#   → READINESS (worker/model/port aware) → COMMAND → DRAIN → VERIFIED STOP
#   → TREE TERMINATION → PORT RELEASE → GPU RELEASE → RELEASE LOCK
#
# This wrapper only parses the historical CLI/env contract and execs the
# supervisor (same pid, so signals reach the one process that cleans up).
# Failure paths run the same cleanup. A server that survives SIGINT+SIGTERM
# is never SIGKILLed: the lifecycle ends BLOCKED and later GPU work is
# refused until `gpu_lock.py unblock --yes`.
#
# Usage:
#   bash scripts/campaign_ops/run_with_server.sh --log-dir D [--port 31000] \
#        [--health-timeout-s 1800] [--readiness-check 1] -- <command...>
#
# Exit: command's rc on a clean lifecycle; 1 on any lifecycle failure (never
# hidden behind a zero rc); 128+sig on signals (after cleanup).
set -uo pipefail

WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PORT="${RWS_PORT:-31000}"
HOST="${RWS_HOST:-127.0.0.1}"
LOG_DIR="${RWS_LOG_DIR:-$WS/logs}"
WHO="${RWS_LOCK_WHO:-rc41-lifecycle-$(date -u +%Y%m%dT%H%M%SZ)}"
HEALTH_TIMEOUT_S="${RWS_HEALTH_TIMEOUT_S:-1800}"
HEALTH_POLL_S="${RWS_HEALTH_POLL_S:-5}"
GPU_LOCK_WAIT_S="${RWS_GPU_LOCK_WAIT_S:-7200}"
EXPECT_ARCH="${YUE2_EXPECT_GPU_ARCH:-gfx1100}"
VENV="${YUE2_VENV:-$WS/environments/yue2-gfx1100}"
PY_B="$VENV/bin/python"
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

SUP=(
  --who "$WHO"
  --workspace "$WS"
  --venv "$VENV"
  --host "$HOST"
  --port "$PORT"
  --log-dir "$LOG_DIR"
  --serve-script "${YUE2_SERVE_SCRIPT:-$REPO/scripts/serve_yue2_gfx1100.sh}"
  --model "${MODEL_PATH:-$WS/models/YuE2-3B}"
  --vae "${VAE_PATH:-$WS/models/YuE2-Vae-legacy}"
  --expect-arch "$EXPECT_ARCH"
  --health-timeout-s "$HEALTH_TIMEOUT_S"
  --health-poll-s "$HEALTH_POLL_S"
  --readiness-check "$READINESS_CHECK"
  --wait-s "$GPU_LOCK_WAIT_S"
  --poll-s 2
  --receipt-dir "$LOG_DIR/rws_server_identity"
  --identity-dir "$LOG_DIR/rws_gpu_identity"
  --boot-log "$LOG_DIR/rws_server_boot.log"
  --server-log "$LOG_DIR/server_yue2_gfx1100.log"
  --drain-s "${RWS_DRAIN_S:-600}"
  --port-release-timeout-s "${RWS_PORT_RELEASE_TIMEOUT_S:-60}"
  --gpu-release-timeout-s "${RWS_GPU_RELEASE_TIMEOUT_S:-180}")
[ -n "${YUE2_GPU_LOCK:-}" ] && SUP+=(--lock "$YUE2_GPU_LOCK")
[ -n "${YUE2_EXPECT_GPU_BDF:-}" ] && SUP+=(--expect-bdf "$YUE2_EXPECT_GPU_BDF")
[ -n "${RWS_STOP_TIMEOUT_S:-}" ] && SUP+=(--stop-timeout-s "$RWS_STOP_TIMEOUT_S")
[ -n "${RWS_CMD_DRAIN_S:-}" ] && SUP+=(--cmd-drain-s "$RWS_CMD_DRAIN_S")
[ -n "${RWS_CANARY_DIR:-}" ] && SUP+=(--canary-dir "$RWS_CANARY_DIR")
[ -n "${RWS_PROGRESS_FILE:-}" ] && SUP+=(--progress-file "$RWS_PROGRESS_FILE")

# exec: this shell BECOMES the supervisor — there is no second process that
# could outlive the lock or clean up after it.
exec "$PY_B" "$REPO/scripts/gpu_lifecycle.py" "${SUP[@]}" -- "${CMD[@]}"
