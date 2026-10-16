#!/usr/bin/env bash
# serve_omni_yue2_gfx1100_capfix.sh - same as serve_omni_yue2_gfx1100.sh but
# imports sglang_omni from the cap-fix worktree (bench/omni-wsb-capfix @
# c853135a) whose only delta is the YuE2 input-cap exemption. Used to serve
# WSB prompt 164 (nested input 4194 chars > generic 4096 cap). Model code is
# byte-identical to the pinned c4841f0c tree; only input validation differs.
set -euo pipefail

VENV=/workspace/yue2-omni-pr/env-omni-rocm
WS164=/workspace/yue2-omni-pr/repo-ws164
MODEL_PATH=/workspace/yue2-sglang-rocm-w7900/models/YuE2-3B
VAE_PATH=/workspace/yue2-sglang-rocm-w7900/models/YuE2-Vae-legacy
HOST=127.0.0.1
PORT=32100
LOG=/workspace/yue2-omni-pr/bench/server_omni_capfix.log

mkdir -p "$(dirname "$LOG")"
export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$WS164"
export ROCR_VISIBLE_DEVICES=0
export SGLANG_YUE2_VAE_DIR="$VAE_PATH"
export SGLANG_YUE2_BATCH_MAX_SIZE=1

{
  echo "=== serve_omni_yue2_gfx1100_capfix $(date -u +%FT%TZ) ==="
  echo "worktree=$(git -C "$WS164" rev-parse HEAD) (cap-fix only delta)"
  echo "--- SGLANG_YUE2* env ---"
  env | grep -E '^SGLANG_YUE2' | sort
} >> "$LOG"

exec "$VENV/bin/sgl-omni" serve \
  --model-path "$MODEL_PATH" \
  --host "$HOST" --port "$PORT" \
  --log-level info \
  >> "$LOG" 2>&1
