#!/usr/bin/env bash
# Retry wrapper: lab proxy 503s intermittently (handoff gotcha 5).
set -uo pipefail
export YUE2_WORKSPACE=/data/yue2
export HF_HOME=/data/yue2/hf-cache
export HF_HUB_CACHE=/data/yue2/hf-cache/hub
export TMPDIR=/data/yue2/tmp
for i in $(seq 1 20); do
  echo "[retry $i] $(date -u +%FT%TZ) starting download_pins"
  /opt/venv/bin/python /workspace/YuE2-SGLang-ROCm/scripts/download_pins.py --workspace /data/yue2 && { echo "[retry $i] SUCCESS"; exit 0; }
  rc=$?
  echo "[retry $i] failed rc=$rc; sleeping 60s"
  sleep 60
done
echo "GAVE UP AFTER 20 ATTEMPTS"
exit 1
