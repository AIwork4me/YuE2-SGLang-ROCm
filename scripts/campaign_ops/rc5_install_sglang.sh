#!/usr/bin/env bash
# rc5_install_sglang.sh — install the FROZEN latest upstream SGLang tree into
# the RC5 generation venv (editable, --no-deps, --no-build-isolation).
#
# The tree under $SGLANG_SRC must already be checked out at the frozen commit
# (recorded by rc5_freeze_upstream.sh); this script NEVER checks out, pulls or
# applies patches. Whatever is in the tree is what gets imported.
#
# --no-build-isolation is REQUIRED: pip's isolated build env would fetch
# sglang's build requirement torch==2.14.1 (CUDA) — the exact CUDA-replacement
# hazard this stack exists to prevent. Never `pip install sgl-kernel` on ROCm.
set -euo pipefail

REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WS="${YUE2_WORKSPACE:-/data/yue2}"
VENV="${YUE2_VENV:-$WS/environments/generation}"
SGLANG_SRC="${YUE2_SGLANG_SRC:-$WS/upstream/sglang-latest}"
LOGDIR="${YUE2_LOG_DIR:-$WS/logs}"
mkdir -p "$LOGDIR" "$WS/tmp_cache"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "--- [1/4] Guard: ROCm torch must stay intact"
python - <<'PY'
import torch
assert torch.__version__ == "2.12.0+rocm7.14.1", torch.__version__
assert torch.version.hip is not None and torch.cuda.is_available()
print("torch guard OK:", torch.__version__)
PY

echo "--- [2/4] Curated dependencies (CUDA-only packages excluded)"
pip install -q -r "$REPO/scripts/sglang-rocm-deps.txt"
pip install -q huggingface_hub hf_transfer soundfile

echo "--- [3/4] SGLang editable install (no deps, no build isolation)"
SGLANG_BUILD_RUST_EXTS=none TMPDIR="$WS/tmp_cache" \
  pip install --no-deps --no-build-isolation -e "$SGLANG_SRC/python"

echo "--- [4/4] Import provenance"
python - "$SGLANG_SRC" <<'PY'
import json, subprocess, sys
import torch, transformers
import sglang
from sglang.srt.models.yue2 import song, fastpath  # noqa: F401
src = sys.argv[1]
head = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"],
                      capture_output=True, text=True, check=True).stdout.strip()
print(json.dumps({"sglang_import_path": sglang.__file__,
                  "torch": torch.__version__, "transformers": transformers.__version__,
                  "sglang_tree_head": head}, indent=1))
PY
pip list --format=freeze > "$LOGDIR/rc5_generation_pip_freeze_full.txt"
echo "Done."
