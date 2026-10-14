#!/usr/bin/env bash
# setup_gfx1100_rocm7141.sh — idempotent installer for the pinned ROCm PyTorch
# stack on gfx1100 (Radeon PRO W7900) per the mission's hard requirement.
#
# - creates (or reuses) an isolated Python 3.12 venv
# - installs the EXACT AMD wheels from repo.amd.com multi-arch index
# - refuses to proceed if a different torch is already present
# - verifies versions + real GPU compute afterwards
# - never touches the host kernel driver or /opt/rocm
# - proxy-aware via standard env vars; no secrets embedded
set -euo pipefail

WORKSPACE="${YUE2_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV="${YUE2_VENV:-$WORKSPACE/environments/yue2-gfx1100}"
LOGDIR="$WORKSPACE/logs"
mkdir -p "$VENV" "$LOGDIR"

echo "[1/5] Python 3.12 venv: $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  python3.12 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "[2/5] Guard: refuse any non-conforming existing torch"
set +e
python - <<'PY'
import sys
try:
    import torch
except ImportError:
    sys.exit(2)   # absent: fine for a fresh install
sys.exit(0 if torch.__version__ == "2.12.0+rocm7.14.1" else 1)
PY
guard_rc=$?
set -e
case $guard_rc in
  0|2) echo "  guard OK (conforming or absent)" ;;
  *)   echo "  FATAL: $VENV has a non-conforming torch; refusing to overwrite." >&2
       echo "  Remove/rename the venv or set YUE2_VENV to a fresh path." >&2
       exit 1 ;;
esac

echo "[3/5] Exact AMD installation command (mission-mandated)"
python -m pip install --upgrade pip setuptools wheel
python -m pip install \
  --index-url https://repo.amd.com/rocm/whl-multi-arch/ \
  "torch[device-gfx1100]==2.12.0+rocm7.14.1" \
  "torchvision[device-gfx1100]==0.27.0+rocm7.14.1" \
  "torchaudio==2.11.0+rocm7.14.1"

echo "[4/5] Record provenance"
python -m pip list --format=freeze > "$LOGDIR/phase1_pip_freeze.txt"

echo "[5/5] Validate versions and real GPU compute"
python - <<'PY'
import torch, torchvision, torchaudio
assert torch.__version__ == "2.12.0+rocm7.14.1"
assert torchvision.__version__ == "0.27.0+rocm7.14.1"
assert torchaudio.__version__ == "2.11.0+rocm7.14.1"
assert torch.version.hip is not None and torch.version.cuda is None
assert torch.cuda.is_available()
assert "gfx1100" in torch.cuda.get_device_properties(0).gcnArchName
for dt in (torch.float32, torch.float16, torch.bfloat16):
    c = torch.randn(1024, 1024, device="cuda").to(dt) @ torch.randn(1024, 1024, device="cuda").to(dt)
    torch.cuda.synchronize()
    assert torch.isfinite(c).all()
print("SETUP OK:", torch.cuda.get_device_name(0), torch.__version__)
PY
echo "Done. Activate with: source $VENV/bin/activate"
echo "Note: 'import torch' auto-initializes the venv ROCm 7.14.1 userspace (torch._rocm_init)."
