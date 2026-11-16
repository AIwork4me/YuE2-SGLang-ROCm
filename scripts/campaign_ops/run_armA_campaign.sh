#!/usr/bin/env bash
# run_armA_campaign.sh — launch the fresh-image Arm A (official PyTorch) full
# WSB campaign, detached, resume-safe, single-GPU (gpu_lock inside the driver).
#
# Hardened (image-swap session, C3 anti-double-launch):
#   * launcher-level flock: only ONE launcher per machine;
#   * if the Arm A driver for THIS run dir is already alive (verified via
#     /proc scan, not pgrep), this invocation is a NO-OP (exit 0) — the resume
#     driver is idempotent, but two writers on one campaign dir are forbidden;
#   * requires the repo checkout and Environment A python to exist.
set -uo pipefail
export YUE2_WORKSPACE=/data/yue2
export HF_HOME=/data/yue2/hf-cache
export HF_HUB_CACHE=/data/yue2/hf-cache/hub
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TMPDIR=/data/yue2/tmp
cd /workspace/YuE2-SGLang-ROCm
RUN_ID=armA_full_20261115f
RUNS_DIR=/data/yue2-runs/armA_wsb_full
LOG=/data/yue2/logs/armA_${RUN_ID}.log
PY=/data/yue2/environments/yue2-torch/bin/python

[ -x "$PY" ] || { echo "FATAL: Environment A python missing: $PY (build_envA.sh first)"; exit 2; }

mkdir -p /data/yue2/locks
exec 9>>/data/yue2/locks/armA_launcher.lock
if ! flock -n 9; then
  echo "[launcher] another Arm A launcher instance holds the lock; exiting (no-op)"
  exit 0
fi

# C3: real driver liveness (zombie-safe /proc scan) — no-op if already running
if "$PY" scripts/campaign_ops/driver_alive.py --script run_wsb_torch.py \
      --runs "$RUNS_DIR" >/dev/null 2>&1; then
  echo "[launcher] Arm A driver already alive for $RUNS_DIR; exiting (no-op)"
  exit 0
fi

# Wait for any GPU owner (API acceptance) to finish, bounded
$PY scripts/gpu_lock.py status || true

exec $PY scripts/run_wsb_torch.py \
  --runs "$RUNS_DIR" \
  --run-id $RUN_ID \
  --venv-python $PY \
  --cache-dir /data/yue2/hf-cache/hub \
  >> $LOG 2>&1
