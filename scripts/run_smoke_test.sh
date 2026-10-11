#!/usr/bin/env bash
# Environment smoke test: Phase 0 GPU checks + module imports (no server
# interaction, no large downloads). Safe to run alongside a live benchmark.
set -euo pipefail
WS="${WS:-/home/amd/Desktop/YuE2}"
source "$WS/environments/yue2/bin/activate"
python "$WS/scripts/phase0_gpu_smoke.py"
python - <<'PY'
import torch
assert torch.version.hip and torch.cuda.is_available()
from sglang.srt.models.yue2 import modeling_yue2, modeling_vae  # noqa: F401
from sglang.multimodal_gen.runtime.pipelines import yue2_pipeline  # noqa: F401
print("smoke: torch", torch.__version__, "| yue2 modules import OK")
PY
echo "SMOKE PASS"
