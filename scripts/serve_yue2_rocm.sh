#!/usr/bin/env bash
# Phase 4+: launch the YuE2 SGLang server on gfx1151 (ROCm).
# Adapted from the PR's H800 script with machine-specific paths removed:
#   - /raid/yiakwy -> $WS/models
#   - CUDA_VISIBLE_DEVICES=5 -> runtime-discovered (single iGPU: device 0)
# ROCm flag matrix per reports/PHASE3_ROCM_RCA.md §4.
set -euo pipefail
WS="${WS:-/home/amd/Desktop/YuE2}"
MODEL_PATH="${MODEL_PATH:-$WS/models/YuE2-3B}"
VAE_PATH="${VAE_PATH:-$WS/models/YuE2-Vae-legacy}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-30065}"
LOG="$WS/logs/server_yue2.log"

source "$WS/environments/yue2/bin/activate"

export SGLANG_YUE2_VAE_DIR="$VAE_PATH"
export FLASHINFER_DISABLE_VERSION_CHECK=1   # harmless without flashinfer; matches PR recipe
# ROCm correctness-first configuration (Phase 3):
export SGLANG_YUE2_FAST_SAMPLER=0   # DeepSelect kernel unavailable on gfx1151
export SGLANG_YUE2_STEP_GRAPH=0    # fused decode+sample graph needs DeepSelect
export SGLANG_YUE2_FUSED_DECODE=0  # sgl_kernel absent
export SGLANG_YUE2_FAST_NAR=0      # fused NAR needs sgl_kernel
export SGLANG_YUE2_FA3=0           # use native ATen flash (validated) via fa3 fallback
export SGLANG_YUE2_BATCHED_AR=0    # BatchedGraphSampler needs DeepSelect
export SGLANG_YUE2_SESSION=1       # session GraphAR works (HIP graphs + ATen flash)
export SGLANG_YUE2_GRAPH_POOL=1
# Single-GPU APU: no CUDA_VISIBLE_DEVICES pinning (device 0 is the only GPU).

mkdir -p "$(dirname "$LOG")"
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
