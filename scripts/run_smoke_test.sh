#!/usr/bin/env bash
# Environment smoke test: Phase 0 GPU checks + module imports (no server
# interaction, no large downloads). Safe to run alongside a live benchmark.
#
# RC4 M1.5 fix: this script previously activated $WS/environments/yue2 (a
# stale workspace layout name that no longer exists) and sourced
# phase0_gpu_smoke.py from $WS/scripts — failing on every current workspace
# (reproduced 2026-11-22 on the fresh clone: "environments/yue2/bin/activate:
# No such file or directory"). It now resolves the venv via YUE2_VENV (default
# $WS/environments/yue2-gfx1100) and runs the repo's own phase0 script.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="${YUE2_WORKSPACE:-$(python3 "$SCRIPT_DIR/yue2_workspace.py" 2>/dev/null || echo /nonexistent)}"
VENV="${YUE2_VENV:-$WS/environments/yue2-gfx1100}"
[ -f "$VENV/bin/activate" ] || { echo "FATAL: venv not found: $VENV (set YUE2_VENV)" >&2; exit 2; }
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python "$SCRIPT_DIR/phase0_gpu_smoke.py"
python - <<'PY'
import torch
assert torch.version.hip and torch.cuda.is_available()
from sglang.srt.models.yue2 import modeling_yue2, modeling_vae  # noqa: F401
from sglang.multimodal_gen.runtime.pipelines import yue2_pipeline  # noqa: F401
print("smoke: torch", torch.__version__, "| yue2 modules import OK")
PY
echo "SMOKE PASS"
