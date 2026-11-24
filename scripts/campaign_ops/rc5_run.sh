#!/usr/bin/env bash
# rc5_run.sh — ONE RC5 generation session (ARM_B_LATEST_UPSTREAM_RC5).
#
# Runs the RC5 campaign driver under the single-owner lifecycle supervisor
# (scripts/gpu_lifecycle.py via run_with_server.sh):
#
#   ACQUIRE GPU LOCK → GPU IDENTITY (physical binding) → GPU IDLE → LAUNCH
#   SERVER → HEALTH → IDENTITY → READINESS → rc5_generate.py → DRAIN →
#   VERIFIED STOP → TREE/PORT/GPU RELEASE → RELEASE LOCK
#
# The driver resumes: verified candidates are skipped, missing or damaged
# ones are regenerated (damaged bundles are quarantined, never deleted).
#
# Usage:
#   bash scripts/campaign_ops/rc5_run.sh <run_dir> <run_id> [prompt_index ...]
#
# Env (all optional):
#   RC5_PORT=31000            RC5_EXPECT_GPU_BDF=   (empty: the single bound GPU)
#   RC5_BACKUP_DIR=           RC5_BACKUP_CLASS=     (disclosed destination class)
#   RC5_CHECKPOINT_EVERY=16   RC5_GPU_LOCK_WAIT_S=60
set -uo pipefail

WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_DIR="$1"
RUN_ID="$2"
shift 2
IDX=("$@")
PORT="${RC5_PORT:-31000}"
PY_B="${YUE2_VENV:-$WS/environments/yue2-gfx1100}/bin/python"
[ -x "$PY_B" ] || PY_B="$(command -v python3)"

[ -n "$RUN_DIR" ] && [ -n "$RUN_ID" ] || {
  echo "usage: rc5_run.sh <run_dir> <run_id> [prompt_index ...]" >&2; exit 2; }
[ -x "$PY_B" ] || { echo "FATAL: generation python missing: $PY_B" >&2; exit 2; }
mkdir -p "$RUN_DIR/lifecycle"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="$RUN_DIR/lifecycle/${STAMP}-$$"
mkdir -p "$LOG_DIR"

export YUE2_WORKSPACE="$WS" YUE2_REPO="$REPO"
export RWS_LOG_DIR="$LOG_DIR"
export RWS_LOCK_WHO="rc5-campaign:${RUN_ID}"
export RWS_GPU_LOCK_WAIT_S="${RC5_GPU_LOCK_WAIT_S:-60}"
export RWS_CMD_DRAIN_S="${RC5_CMD_DRAIN_S:-2400}"
export YUE2_EXPECT_GPU_ARCH="${YUE2_EXPECT_GPU_ARCH:-gfx1100}"
export YUE2_EXPECT_GPU_BDF="${RC5_EXPECT_GPU_BDF:-}"
export YUE2_FINALIZE_LOG="$LOG_DIR/finalize_invocations.log"
# RC5 serves with the upstream NATIVE capability gates (no force-flags)
export YUE2_SERVE_SCRIPT="${YUE2_SERVE_SCRIPT:-$REPO/scripts/serve_yue2_rc5.sh}"

ARGS=(--workspace "$WS" --run-dir "$RUN_DIR" --run-id "$RUN_ID"
      --server "http://127.0.0.1:$PORT"
      --gpu-receipt "$LOG_DIR/rws_gpu_identity/pre_boot_gpu_identity.json"
      --server-receipt "$LOG_DIR/rws_server_identity/server-identity.json"
      --server-log "$LOG_DIR/server_yue2_gfx1100.log"
      --checkpoint-every "${RC5_CHECKPOINT_EVERY:-16}")
[ ${#IDX[@]} -gt 0 ] && ARGS+=(--indices "${IDX[@]}")
[ -n "${RC5_BACKUP_DIR:-}" ] && ARGS+=(--backup-dir "$RC5_BACKUP_DIR"
                                        --backup-class "${RC5_BACKUP_CLASS:-UNSPECIFIED}")

# no exec-into-git, no push, no branch handling: this script only generates
exec bash "$REPO/scripts/campaign_ops/run_with_server.sh" \
  --log-dir "$LOG_DIR" --port "$PORT" -- \
  "$PY_B" "$REPO/scripts/rc5_generate.py" "${ARGS[@]}"
