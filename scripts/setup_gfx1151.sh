#!/usr/bin/env bash
# Phase 1: reproducible gfx1151 ROCm 7.14.1 environment for SGLang PR #42106 (YuE2).
#
# Strategy (see reports/PHASE1_INSTALLATION.md):
#  - ROCm PyTorch stack from AMD's multi-arch wheel index (torch 2.12.0+rocm7.14.1,
#    torchvision 0.27.0, torchaudio 2.11.0, device extra gfx1151). The wheels bundle
#    the ROCm 7.14.1 userspace, so the host's ROCm 7.2.1 userspace and the in-tree
#    amdgpu kernel driver are left untouched.
#  - SGLang installed EDITABLE from the pinned PR checkout with --no-deps, because
#    its metadata pins torch==2.14.1 (CUDA) and CUDA-only extras
#    (flashinfer_python[cu13], sgl-kernel family, deep_ep/deep_gemm, ...).
#  - The remainder of SGLang's dependency set is installed selectively, skipping
#    NVIDIA-only packages. Nothing may replace the ROCm torch (mission rule 7).
set -euo pipefail

WS="${WS:-/home/amd/Desktop/YuE2}"
VENV="${VENV:-$WS/environments/yue2}"
SGLANG_SRC="$WS/upstream/sglang"
AMD_INDEX="https://repo.amd.com/rocm/whl-multi-arch/"
LOG="$WS/logs/phase1.log"

if [ ! -x "$VENV/bin/python" ]; then
  echo "--- creating fresh venv at $VENV ---"
  uv venv --python 3.12 "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
exec >>"$LOG" 2>&1
echo "=== setup_gfx1151.sh started: $(date -Is) ==="

command -v uv >/dev/null || python -m pip install -q uv

echo "--- [1/5] ROCm PyTorch (idempotent) ---"
if ! python -c "import torch; assert torch.version.hip and torch.cuda.is_available()" 2>/dev/null; then
  uv pip install --index-url "$AMD_INDEX" \
    "torch[device-gfx1151]==2.12.0+rocm7.14.1" \
    "torchvision[device-gfx1151]==0.27.0+rocm7.14.1" \
    "torchaudio==2.11.0+rocm7.14.1"
fi
python - <<'PY'
import torch
print("torch", torch.__version__, "hip", torch.version.hip, "dev", torch.cuda.get_device_name(0))
PY

echo "--- [2/5] Hugging Face tooling + mirrors ---"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HUB_ENABLE_HF_TRANSFER=1
uv pip install -q "huggingface_hub" "hf_transfer"

echo "--- [3/5] SGLang editable install (no deps) from pinned PR checkout ---"
SGLANG_BUILD_RUST_EXTS=none uv pip install --no-deps -e "$SGLANG_SRC/python"

echo "--- [4/5] Curated dependency set (CUDA-only packages excluded) ---"
# Mirrors python/pyproject.toml `dependencies` of the PR, minus:
#   torch/torchvision/torchaudio (pinned to CUDA 2.14.1 upstream; we keep ROCm 2.12.0)
#   cuda-python, cuda-tile, flashinfer_python[cu13], humming-kernels[cu13],
#   nvidia-cutlass-dsl[cu13], nvidia-mathdx, nvshmem4py-cu13, flash-attn-4,
#   sgl-deep-ep, sgl-deep-gemm, sglang-kernel, quack-kernels, tilelang,
#   tokenspeed_mla, torch_memory_saver, torchcodec  (CUDA-only or CUDA-first;
#   availability/impact audited in evidence/dependency_matrix.json)
uv pip install -q \
  aiohttp "anthropic>=0.20.0" "blobfile==3.0.0" build "compressed-tensors==0.18.0" \
  datasets distro easydict einops fastapi gguf interegular \
  "llguidance>=1.7.6,<2.0.0" "mistral_common>=1.11.5" modelscope msgspec ninja \
  "numba==0.65.1" numpy nvidia-ml-py "openai==2.6.1" "openai-harmony==0.0.4" \
  orjson "outlines==0.1.11" packaging partial_json_parser pillow \
  "prometheus-client>=0.20.0" psutil py-spy pybase64 pydantic python-multipart \
  "pyzmq>=25.1.2" regex requests scipy "sentencepiece==0.2.1" setproctitle \
  "smg-grpc-servicer>=0.9.0" "soundfile==0.13.1" tiktoken "timm==1.0.16" \
  "tokenizers==0.23.2" tqdm "transformers==5.17.0" uvicorn uvloop watchfiles \
  "xgrammar==0.2.7" xxhash zstandard "apache-tvm-ffi==0.1.11" IPython \
  "kernels>=0.14.1,<0.15" outlines imageio imageio-ffmpeg diffusers addict cache-dit

echo "--- [5/5] Verification ---"
python - <<'PY'
import torch, torch.version
print("torch:", torch.__version__, "| hip:", torch.version.hip)
x = torch.randn(512, 512, device="cuda", dtype=torch.bfloat16)
y = (x @ x).float().sum()
torch.cuda.synchronize()
assert torch.isfinite(y).item(), "bf16 GPU compute broken"
print("bf16 GPU matmul OK, checksum:", float(y))
import sglang
from sglang.srt.models.yue2 import modeling_yue2, modeling_vae
from sglang.multimodal_gen.runtime.pipelines import yue2_pipeline
print("sglang import OK; yue2 modules import OK")
PY
python -m pip check || echo "NOTE: pip check reports conflicts (expected: sglang metadata pins torch==2.14.1 CUDA); see dependency_matrix.json"
echo "=== setup_gfx1151.sh finished: $(date -Is) ==="
