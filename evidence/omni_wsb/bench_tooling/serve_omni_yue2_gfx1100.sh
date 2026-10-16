#!/usr/bin/env bash
# serve_omni_yue2_gfx1100.sh - launch the patched SGLang-Omni YuE2 server on
# gfx1100 for the arm-B WSB benchmark. Bench tree (bench/omni-wsb) ONLY.
# SGLANG_YUE2_BATCH_MAX_SIZE=1 mirrors the validated http-e2e launch and keeps
# generation strictly serial (one candidate in flight).
set -euo pipefail

VENV=/workspace/yue2-omni-pr/env-omni-rocm
REPO=/workspace/yue2-omni-pr/repo
MODEL_PATH=/workspace/yue2-sglang-rocm-w7900/models/YuE2-3B
VAE_PATH=/workspace/yue2-sglang-rocm-w7900/models/YuE2-Vae-legacy
HOST=127.0.0.1
PORT=${OMNI_PORT:-32100}
LOG=${OMNI_SERVE_LOG:-/workspace/yue2-omni-pr/bench/server_omni.log}

mkdir -p "$(dirname "$LOG")"
export PATH="$VENV/bin:$PATH"
export ROCR_VISIBLE_DEVICES=0
export SGLANG_YUE2_VAE_DIR="$VAE_PATH"
export SGLANG_YUE2_BATCH_MAX_SIZE=1

{
  echo "=== serve_omni_yue2_gfx1100 $(date -u +%FT%TZ) ==="
  echo "omni_tree=$(git -C "$REPO" rev-parse HEAD) branch=$(git -C "$REPO" branch --show-current)"
  echo "pr1_head=50c91c0888312ae784d3c42d9536665aa517dd9d author_base=85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9"
  git -C "$REPO" status --short | head -3
  echo "--- SGLANG_YUE2* env ---"
  env | grep -E '^SGLANG_YUE2' | sort
  "$VENV/bin/python" - <<'PY'
import torch, sglang_omni
print("torch", torch.__version__, "hip", torch.version.hip)
print("sglang_omni", sglang_omni.__version__, torch.cuda.get_device_name(0))
PY
} >> "$LOG"

exec "$VENV/bin/sgl-omni" serve \
  --model-path "$MODEL_PATH" \
  --host "$HOST" --port "$PORT" \
  --log-level info \
  >> "$LOG" 2>&1
