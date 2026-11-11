#!/usr/bin/env bash
# setup_sglang_gfx1100.sh — SGLang yue2 serving stack on the W7900 (gfx1100).
#
# Prerequisites (idempotent, separate steps):
#   1. scripts/setup_gfx1100_rocm7141.sh  (torch 2.12.0+rocm7.14.1 venv)
#   2. scripts/download_pins.py           (models + SGLang PR tarball)
#   3. patches 0001-0005 + 0008 applied to $WS/upstream/sglang
#
# This script installs the curated SGLang dependency set (no CUDA-only
# packages; scripts/sglang-rocm-deps.txt) plus SGLang itself EDITABLE with
# --no-deps from the pinned PR checkout, then verifies imports.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WS="${YUE2_WORKSPACE:-$(python3 "$SCRIPT_DIR/yue2_workspace.py" 2>/dev/null || true)}"
if [ -z "${WS}" ]; then
  echo "FATAL: cannot resolve workspace; set YUE2_WORKSPACE" >&2; exit 2
fi
VENV="${YUE2_VENV:-$WS/environments/yue2-gfx1100}"
SGLANG_SRC="$WS/upstream/sglang"
LOG="$WS/logs/setup_sglang_gfx1100.log"

[ -x "$VENV/bin/python" ] || { echo "FATAL: $VENV missing (run setup_gfx1100_rocm7141.sh first)" >&2; exit 2; }
[ -f "$SGLANG_SRC/python/pyproject.toml" ] || { echo "FATAL: $SGLANG_SRC missing (run download_pins.py + apply patches)" >&2; exit 2; }

mkdir -p "$WS/logs"
exec >>"$LOG" 2>&1
echo "=== setup_sglang_gfx1100.sh started: $(date -Is) ==="
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "--- [1/3] Guard: ROCm torch must stay intact ---"
python - <<'PY'
import torch
assert torch.__version__ == "2.12.0+rocm7.14.1", torch.__version__
assert torch.version.hip is not None and torch.cuda.is_available()
print("torch guard OK:", torch.__version__)
PY

echo "--- [2/3] Curated dependencies (CUDA-only packages excluded) ---"
pip install -q -r "$SCRIPT_DIR/sglang-rocm-deps.txt"
pip install -q "huggingface_hub" "hf_transfer"

echo "--- [3/3] SGLang editable install (no deps, no build isolation) from pinned PR checkout ---"
# --no-build-isolation is REQUIRED: pip's isolated build env would fetch
# sglang's build requirements including torch==2.14.1 (CUDA) — the exact
# CUDA-replacement hazard this stack exists to prevent. The venv already has
# setuptools + the ROCm torch that the build introspects.
SGLANG_BUILD_RUST_EXTS=none TMPDIR="$WS/tmp_cache" pip install --no-deps --no-build-isolation -e "$SGLANG_SRC/python"

echo "--- Verification ---"
python - <<'PY'
import torch, transformers
import sglang
from sglang.srt.models.yue2 import song, fastpath
print("sglang import OK | torch", torch.__version__, "| transformers", transformers.__version__)
PY
pip list --format=freeze > "$WS/logs/sglang_gfx1100_pip_freeze.txt"
echo "Done. Activate: source $VENV/bin/activate"
