#!/usr/bin/env bash
# rc5_build_generation_env.sh — RC5 generation environment (isolated venv).
#
# Reproduces the historically validated W7900 serving stack in an isolated
# Python 3.12 venv:
#   torch 2.12.0+rocm7.14.1 (device-gfx1100) + torchvision 0.27.0 + torchaudio 2.11.0
#   from the AMD multi-arch wheel index (repo.amd.com).
# SGLang itself is NOT installed here: see rc5_install_sglang.sh (latest
# upstream PR #42106 head, frozen SHA, patch reconciliation recorded).
#
# Never touches the host kernel driver, /opt/rocm or the system python.
# Idempotent: refuses to proceed if a non-conforming torch is present.
set -euo pipefail

WS="${YUE2_WORKSPACE:-/data/yue2}"
VENV="${YUE2_VENV:-$WS/environments/generation}"
LEGACY_LINK="${YUE2_VENV_LEGACY_LINK:-$WS/environments/yue2-gfx1100}"
LOGDIR="${YUE2_LOG_DIR:-$WS/logs}"
AMD_INDEX="${YUE2_AMD_WHL_INDEX:-https://repo.amd.com/rocm/whl-multi-arch/}"
PIP_EXTRA_INDEX="${YUE2_PIP_EXTRA_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export PIP_EXTRA_INDEX_URL="$PIP_EXTRA_INDEX"
export PIP_INDEX_URL="$PIP_EXTRA_INDEX"
mkdir -p "$VENV" "$LOGDIR"

echo "[1/5] Python 3.12 venv: $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  rm -rf "$VENV"
  python3.12 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip setuptools wheel

echo "[2/5] Guard: refuse any non-conforming existing torch"
set +e
python - <<'PY'
import sys
try:
    import torch
except ImportError:
    sys.exit(2)
sys.exit(0 if torch.__version__ == "2.12.0+rocm7.14.1" else 1)
PY
guard_rc=$?
set -e
case $guard_rc in
  0|2) echo "  guard OK (conforming or absent)" ;;
  *)   echo "  FATAL: $VENV has a non-conforming torch; refusing to overwrite." >&2
       exit 1 ;;
esac

echo "[3/5] Exact AMD wheels (historically validated W7900 stack)"
python -m pip install \
  --index-url "$AMD_INDEX" \
  --extra-index-url "$PIP_EXTRA_INDEX" \
  "torch[device-gfx1100]==2.12.0+rocm7.14.1" \
  "torchvision[device-gfx1100]==0.27.0+rocm7.14.1" \
  "torchaudio==2.11.0+rocm7.14.1"

# RC6.1 M3.4/M5: download_pins (install step 2/5) needs huggingface_hub in the
# generation venv BEFORE rc5_install_sglang.sh runs (step 5/5 installs it too —
# idempotent). Without this, a FRESH workspace install fails at step 2 with
# ModuleNotFoundError (live defect found during the RC6.1 fresh-clone replay).
python -m pip install -q huggingface_hub

echo "[4/5] Record provenance"
python -m pip list --format=freeze > "$LOGDIR/rc5_generation_pip_freeze_step1.txt"

echo "[5/5] Validate versions and real GPU compute"
python - <<'PY'
import torch, torchvision, torchaudio
assert torch.__version__ == "2.12.0+rocm7.14.1", torch.__version__
assert torchvision.__version__ == "0.27.0+rocm7.14.1", torchvision.__version__
assert torchaudio.__version__ == "2.11.0+rocm7.14.1", torchaudio.__version__
assert torch.version.hip is not None and torch.version.cuda is None
assert torch.cuda.is_available()
p = torch.cuda.get_device_properties(0)
assert "gfx1100" in p.gcnArchName, p.gcnArchName
for dt in (torch.float32, torch.float16, torch.bfloat16):
    c = torch.randn(1024, 1024, device="cuda").to(dt) @ torch.randn(1024, 1024, device="cuda").to(dt)
    torch.cuda.synchronize()
    assert torch.isfinite(c).all()
print("SETUP OK:", torch.cuda.get_device_name(0), torch.__version__, "| hip", torch.version.hip)
PY

# backward-compatible alias used by the historical launcher scripts
if [ ! -e "$LEGACY_LINK" ]; then
  ln -s "$(basename "$VENV")" "$LEGACY_LINK"
  echo "legacy alias: $LEGACY_LINK -> $VENV"
fi
echo "Done. Activate with: source $VENV/bin/activate"
