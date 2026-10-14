#!/usr/bin/env bash
# serve_yue2_gfx1100.sh - launch the YuE2 SGLang server on gfx1100 (W7900).
# Portable: all paths from env; verifies torch stack; logs config; safe device use.
set -euo pipefail

WS="${YUE2_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV="${YUE2_VENV:-$WS/environments/yue2-gfx1100}"
MODEL_PATH="${MODEL_PATH:-$WS/models/YuE2-3B}"
VAE_PATH="${VAE_PATH:-$WS/models/YuE2-Vae-legacy}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-31000}"
LOG="${LOG:-$WS/logs/server_yue2_gfx1100.log}"
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
# ROCm correctness-first flag matrix (Phase 4 RCA; patches enforce the same)
export SGLANG_YUE2_FAST_SAMPLER=0   # DeepSelect CUDA-only JIT kernel
export SGLANG_YUE2_STEP_GRAPH=0     # fused decode+sample needs DeepSelect
export SGLANG_YUE2_FUSED_DECODE=0   # sgl_kernel absent on ROCm
export SGLANG_YUE2_FAST_NAR=0       # fused NAR needs sgl_kernel
export SGLANG_YUE2_FA3=0            # shared FA wrapper -> ATen native flash (validated)
export SGLANG_YUE2_BATCHED_AR=0     # BatchedGraphSampler needs DeepSelect
export SGLANG_YUE2_SESSION=1        # session GraphAR works (HIP graphs + ATen flash)
export SGLANG_YUE2_GRAPH_POOL=1

mkdir -p "$(dirname "$LOG")"
{
  echo "=== serve_yue2_gfx1100 $(date -u +%FT%TZ) ==="
  echo "model=$MODEL_PATH vae=$VAE_PATH host=$HOST port=$PORT gpu=$GPU_ID"
  echo "flags: FAST_SAMPLER=0 STEP_GRAPH=0 FUSED_DECODE=0 FAST_NAR=0 FA3=0 BATCHED_AR=0 SESSION=1 GRAPH_POOL=1"
  env | grep -E '^SGLANG_YUE2|^ROCR_VISIBLE' | sort
} >> "$LOG"

echo "launching sglang serve on $HOST:$PORT (log: $LOG)"
exec sglang serve \
  --model-path "$MODEL_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  --num-gpus 1 \
  --ulysses-degree 1 \
  --ring-degree 1 \
  --warmup-mode off \
  >>"$LOG" 2>&1
