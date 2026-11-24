#!/usr/bin/env bash
# serve_yue2_rc5.sh - launch the YuE2 SGLang server on gfx1100 (W7900) with the
# UPSTREAM NATIVE capability gates (RC5).
#
# Difference to serve_yue2_gfx1100.sh: no SGLANG_YUE2_* force-flags. Since the
# author's commit 2a816358d ("enable ROCm fallback while preserving CUDA fast
# paths") the tree gates every CUDA-only fast path on real capability:
#   fastpath.deepselect_runnable()  -> reference sampler / looped AR
#   fa3._shared_fa3_usable()        -> native ATen varlen flash on HIP
#   batched.batched_ar_enabled()    -> per-request AR without DeepSelect
# so the fallback is the author's code, not an operator override. The path
# actually taken is exported per request in plan.json ("execution",
# "attention", "sampler") and journaled for every candidate.
set -euo pipefail

WS="${YUE2_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV="${YUE2_VENV:-$WS/environments/yue2-gfx1100}"
MODEL_PATH="${MODEL_PATH:-$WS/models/YuE2-3B}"
VAE_PATH="${VAE_PATH:-$WS/models/YuE2-Vae-legacy}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-31000}"
# SERVER_LOG is a FILE (the legacy LOG variable could name a directory).
SERVER_LOG="${SERVER_LOG:-$WS/logs/server_yue2_gfx1100.log}"
GPU_ID="${GPU_ID:-0}"

source "$VENV/bin/activate"

# verify the exact ROCm torch stack before touching the GPU
python - <<'PY'
import torch
assert torch.__version__ == "2.12.0+rocm7.14.1", torch.__version__
assert torch.version.cuda is None and torch.version.hip is not None
assert "gfx1100" in torch.cuda.get_device_properties(0).gcnArchName
print("torch stack OK:", torch.__version__, "| device:", torch.cuda.get_device_name(0))
PY

export ROCR_VISIBLE_DEVICES="$GPU_ID"
export SGLANG_YUE2_VAE_DIR="$VAE_PATH"
export FLASHINFER_DISABLE_VERSION_CHECK=1

mkdir -p "$(dirname "$SERVER_LOG")"
SGLANG_IMPORT="$(python -c 'import sglang; print(sglang.__file__)' 2>/dev/null | tail -1)"
{
  echo "=== serve_yue2_rc5 $(date -u +%FT%TZ) ==="
  echo "model=$MODEL_PATH vae=$VAE_PATH host=$HOST port=$PORT gpu=$GPU_ID"
  echo "flags: NATIVE CAPABILITY GATES (no SGLANG_YUE2_* override set)"
  echo "sglang_import=$SGLANG_IMPORT"
  env | grep -E '^SGLANG_YUE2|^ROCR_VISIBLE' | sort
} >> "$SERVER_LOG"

echo "launching sglang serve on $HOST:$PORT (log: $SERVER_LOG)"
exec sglang serve \
  --model-path "$MODEL_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  --num-gpus 1 \
  --ulysses-degree 1 \
  --ring-degree 1 \
  --warmup-mode off \
  >>"$SERVER_LOG" 2>&1
