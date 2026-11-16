#!/usr/bin/env bash
# Environment B — SGLang ROCm serving arm (torch 2.12.0+rocm7.14.1 device-gfx1100).
set -uo pipefail
export YUE2_WORKSPACE=/data/yue2
export YUE2_VENV=/data/yue2/environments/yue2-gfx1100
export TMPDIR=/data/yue2/tmp
for i in $(seq 1 5); do
  bash /workspace/YuE2-SGLang-ROCm/scripts/setup_gfx1100_rocm7141.sh && { echo ENV_B_BASE_OK; break; }
  echo "[build_envB retry $i]"; sleep 60
done
[ -d /data/yue2/upstream/sglang/.git ] || { echo "sglang tree missing"; exit 1; }
for i in $(seq 1 5); do
  YUE2_WORKSPACE=/data/yue2 bash /workspace/YuE2-SGLang-ROCm/scripts/setup_sglang_gfx1100.sh && { echo ENV_B_SGLANG_OK; exit 0; }
  echo "[sglang retry $i]"; sleep 60
done
exit 1
