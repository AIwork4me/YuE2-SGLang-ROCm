#!/usr/bin/env bash
# Environment A — official native PyTorch benchmark arm (frozen pins).
set -euo pipefail
WS=/data/yue2
VENV=$WS/environments/yue2-torch
export TMPDIR=$WS/tmp
for i in $(seq 1 10); do
  /usr/bin/python3.12 -m venv "$VENV" 2>/dev/null || true
  [ -x "$VENV/bin/python" ] && break
  sleep 5
done
retry() { for i in $(seq 1 6); do "$@" && return 0; echo "[retry $i] $*"; sleep 30; done; return 1; }
retry "$VENV/bin/pip" install --quiet --upgrade pip wheel setuptools
retry "$VENV/bin/pip" install --quiet \
  --index-url https://download.pytorch.org/whl/rocm7.1 \
  "torch==2.10.0+rocm7.1" "torchaudio==2.10.0+rocm7.1"
retry "$VENV/bin/pip" install --quiet \
  "transformers==4.57.6" "safetensors==0.7.0" "tiktoken==0.12.0" "numpy==2.2.6" \
  "soundfile==0.13.1" "accelerate==1.13.0" "huggingface-hub==0.36.2"
"$VENV/bin/pip" install --quiet --no-deps "$WS/models/YuE2-3B/yue2_infer-0.1.3-py3-none-any.whl"
"$VENV/bin/pip" check
"$VENV/bin/python" - <<'PY'
import torch, transformers
assert torch.cuda.is_available(), "CUDA/HIP unavailable in env A"
assert "+rocm" in torch.__version__, torch.__version__
print("ENV-A-OK", "python", __import__("sys").version.split()[0],
      "torch", torch.__version__, "hip", torch.version.hip,
      "transformers", transformers.__version__)
PY
