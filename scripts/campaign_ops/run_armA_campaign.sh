#!/usr/bin/env bash
# run_armA_campaign.sh — launch the fresh-image Arm A (official PyTorch) full
# WSB campaign, detached, resume-safe, single-GPU (gpu_lock inside the driver).
set -uo pipefail
export YUE2_WORKSPACE=/data/yue2
export HF_HOME=/data/yue2/hf-cache
export HF_HUB_CACHE=/data/yue2/hf-cache/hub
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TMPDIR=/data/yue2/tmp
cd /workspace/YuE2-SGLang-ROCm
RUN_ID=armA_full_20261115f
LOG=/data/yue2/logs/armA_${RUN_ID}.log
PY=/data/yue2/environments/yue2-torch/bin/python

# Wait for any GPU owner (API acceptance) to finish, bounded
$PY scripts/gpu_lock.py status || true

exec $PY scripts/run_wsb_torch.py \
  --runs /data/yue2-runs/armA_wsb_full \
  --run-id $RUN_ID \
  --venv-python $PY \
  --cache-dir /data/yue2/hf-cache/hub \
  > $LOG 2>&1
