#!/usr/bin/env bash
# rc5_evaluator_install.sh — official evaluator environments on ROCm (RC5 M5).
#
# 1. `wsb_eval.py prepare --download hf-mirror --install` is the OFFICIAL
#    installer of the frozen bundle (hash-verified asset download, uv-managed
#    Python 3.12.11 venvs from the frozen lock files).
# 2. torch-family substitution (DEV-3, disclosed): the frozen locks pin CUDA
#    torch builds that AMD does not publish for ROCm. Under the documented
#    gate WSB_ROCM_TORCH_OVERRIDE=1 only torch/torchaudio/torchvision/triton
#    are replaced by the historically validated W7900 evaluator wheels
#    (torch 2.10.0+rocm7.14.1); every other lock entry stays exact.
#
# Nothing here touches GPU state: the installer is CPU/network only.
set -uo pipefail

WS="${YUE2_WORKSPACE:-/data/yue2}"
ROOT="${YUE2_EVALUATOR_TREE:-$WS/benchmark/wsb_metrics}"
BOOT_PY="${YUE2_BOOT_PYTHON:-$WS/environments/tools/bin/python}"   # any 3.12 for prepare
METRICS="${RC5_EVAL_METRICS:-per,songbench,mulan,allmusiccaps}"
TORCH_ROCM="${RC5_EVAL_TORCH:-2.10.0+rocm7.14.1}"
TORCHAUDIO_ROCM="${RC5_EVAL_TORCHAUDIO:-2.10.0+rocm7.14.1}"
TORCHVISION_ROCM="${RC5_EVAL_TORCHVISION:-0.25.0+rocm7.14.1}"
AMD_INDEX="${YUE2_AMD_WHL_INDEX:-https://repo.amd.com/rocm/whl-multi-arch/}"
export TMPDIR="$WS/tmp"; mkdir -p "$TMPDIR"
# uv's default HTTP timeout (30 s) is too short behind the egress proxy for
# the ~31 MB python-build-standalone download (RC5-REPRO-4: "Request failed
# after 3 retries ... operation timed out"; 61 s measured at success)
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-600}"
# Optional offline wheel directory (scripts/rc5_prefetch_wheels.py): the SAME
# locked artifacts, fetched with curl instead of uv's slow client. The official
# `prepare` command is unchanged; uv just resolves from the flat directory.
if [ -n "${RC5_WHEEL_DIR:-}" ]; then
  [ -d "$RC5_WHEEL_DIR" ] || { echo "FATAL: RC5_WHEEL_DIR missing: $RC5_WHEEL_DIR"; exit 2; }
  export UV_NO_INDEX=1 UV_FIND_LINKS="$RC5_WHEEL_DIR"
  echo "offline wheel directory: $RC5_WHEEL_DIR ($(ls "$RC5_WHEEL_DIR" | wc -l) files)"
fi
UV="$ROOT/bin/uv"
LOG="$WS/logs/rc5_evaluator_prepare.log"

[ -f "$ROOT/wsb_eval.py" ] || { echo "FATAL: evaluator tree missing: $ROOT (rc5_build_evaluator_tree.sh)"; exit 2; }
[ -x "$BOOT_PY" ] || { echo "FATAL: bootstrap python missing: $BOOT_PY"; exit 2; }

echo "[1/3] official prepare (download $METRICS from hf-mirror + install frozen venvs)"
ok=0
for i in 1 2 3 4 5; do
  if "$BOOT_PY" "$ROOT/wsb_eval.py" prepare --metrics "$METRICS" --download hf-mirror --install >> "$LOG" 2>&1; then
    ok=1; break
  fi
  echo "[prepare retry $i] (log: $LOG)"; sleep 30
done
[ "$ok" = 1 ] || { echo "FATAL: official prepare failed; see $LOG"; tail -30 "$LOG"; exit 1; }
echo "PREPARE_INSTALL_OK"

echo "[2/3] torch-family substitution under the documented ROCm gate"
for role in metrics eval; do
  PY="$ROOT/.venvs/$role/bin/python"
  [ -x "$PY" ] || { echo "  [skip] $role venv absent"; continue; }
  ok=0
  for j in 1 2 3 4 5; do
    if "$UV" pip install --python "$PY" --index-url "$AMD_INDEX" \
        "torch[device-gfx1100]==$TORCH_ROCM" \
        "torchaudio[device-gfx1100]==$TORCHAUDIO_ROCM" \
        "torchvision[device-gfx1100]==$TORCHVISION_ROCM" >> "$LOG" 2>&1; then
      ok=1; break
    fi
    echo "[substitution retry $j for $role]"; sleep 30
  done
  [ "$ok" = 1 ] || { echo "FATAL: torch substitution failed for $role"; exit 1; }
  "$PY" - >> "$LOG" 2>&1 <<'PY'
import torch, torchaudio, torchvision
print("SUBSTITUTED", torch.__version__, torchaudio.__version__, torchvision.__version__, torch.version.hip)
PY
done

echo "[3/3] environment receipts"
mkdir -p "$WS/logs"
for role in metrics eval; do
  PY="$ROOT/.venvs/$role/bin/python"
  [ -x "$PY" ] || continue
  "$UV" pip freeze --python "$PY" > "$WS/logs/rc5_eval_${role}_pip_freeze.txt" 2>/dev/null
  "$PY" -c "import platform, torch; print('$role python', platform.python_version(), 'torch', torch.__version__, 'hip', torch.version.hip)" 2>&1 | grep -v rocSHMEM
done
echo "EVALUATOR_INSTALL_DONE"
