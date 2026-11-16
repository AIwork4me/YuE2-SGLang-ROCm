#!/usr/bin/env bash
set -uo pipefail
export TMPDIR=/data/yue2/tmp
cd /data/yue2/benchmark/WildSongBench/wsb_metrics
for i in $(seq 1 5); do
  /opt/venv/bin/python wsb_eval.py prepare --metrics per,songbench,mulan,allmusiccaps --install && { echo PREPARE_INSTALL_OK; break; }
  echo "[prepare retry $i]"; sleep 30
done
# torch-family substitution under the documented env gate (lock DEV-3):
UV=/data/yue2/benchmark/WildSongBench/wsb_metrics/bin/uv
for role in metrics eval; do
  PY=/data/yue2/benchmark/WildSongBench/wsb_metrics/.venvs/$role/bin/python
  [ -x "$PY" ] || continue
  for j in 1 2 3; do
    "$UV" pip install --python "$PY" \
      --index-url https://repo.amd.com/rocm/whl-multi-arch/ \
      "torch[device-gfx1100]==2.10.0+rocm7.14.1" \
      "torchaudio[device-gfx1100]==2.10.0+rocm7.14.1" \
      "torchvision[device-gfx1100]==0.25.0+rocm7.14.1" && break
    echo "[substitution retry $j for $role]"; sleep 30
  done
done
echo SUBSTITUTION_DONE
