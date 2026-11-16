#!/usr/bin/env bash
set -uo pipefail
export TMPDIR=/data/yue2/tmp
for i in $(seq 1 10); do
  echo "[fetch retry $i] $(date -u +%FT%TZ)"
  /opt/venv/bin/python /workspace/YuE2-SGLang-ROCm/scripts/fetch_eval_assets_hub.py && { echo FETCH_OK; exit 0; }
  sleep 60
done
exit 1
