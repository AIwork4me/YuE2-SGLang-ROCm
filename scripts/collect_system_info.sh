#!/usr/bin/env bash
# Phase 0 system capture. Dumps raw diagnostics to logs/phase0_raw/ and
# builds logs/phase0.log. Safe to re-run; never modifies system state.
set -uo pipefail
WS="${WS:-/home/amd/Desktop/YuE2}"
RAW="$WS/logs/phase0_raw"
mkdir -p "$RAW"

run() { # run <name> <cmd...>
  local name="$1"; shift
  { echo "\$ $*"; "$@" 2>&1; echo "[exit $?]"; } > "$RAW/$name.txt"
  echo "captured $name (exit tail: $(tail -1 "$RAW/$name.txt"))"
}

{
  echo "=== Phase 0 capture started: $(date -Is) ==="
  run uname        uname -a
  run os_release   cat /etc/os-release
  run lsb_release  lsb_release -a
  run cpuinfo      grep -m1 "model name" /proc/cpuinfo
  run cpuinfo_full lscpu
  run rocminfo     rocminfo
  run rocm_smi     rocm-smi
  run amd_smi      amd-smi metric
  run kfd          ls /dev/kfd /dev/dri
  run dri_render   ls -la /dev/dri/by-path 2>/dev/null
  run meminfo      grep -E "MemTotal|MemAvailable|SwapTotal|SwapFree" /proc/meminfo
  run free         free -h
  run df           df -h
  run df_inode     df -i
  run swapon       swapon --show
  run python       python3 --version
  run python_list  bash -c 'python3 -m pip list 2>/dev/null'
  run uv_ver       uv --version
  run git_ver      git --version
  run gh_auth      bash -c 'gh auth status 2>&1 | sed "s/gho_[A-Za-z0-9_]*/<redacted>/"'
  run rocm_ver     bash -c 'cat /opt/rocm/.info/version 2>/dev/null; ls -d /opt/rocm-* 2>/dev/null'
  run dkms         bash -c 'dkms status 2>/dev/null || echo no-dkms'
  run kernel_mod   bash -c 'lsmod | grep -E "amdgpu|amdkfd" | head'
  run amdgpu_params bash -c 'grep -H . /sys/class/drm/card*/device/gtt_size /sys/class/drm/card*/device/vis_vram_total /sys/class/drm/card*/device/mem_info_vram_total 2>/dev/null'
  run env_proxy    bash -c 'env | grep -iE "proxy|hf_endpoint|hugging" | sed "s/=.*[A-Za-z0-9]\{20,\}.*/=<redacted>/" || echo none'
  run net_hf       bash -c 'curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://huggingface.co 2>&1'
  run net_hfmirror bash -c 'curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://hf-mirror.com 2>&1'
  run net_amd      bash -c 'curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://repo.amd.com/rocm/whl-multi-arch/ 2>&1'
  run net_github   bash -c 'curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://github.com 2>&1'
  run net_pypi     bash -c 'curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://pypi.org/simple/ 2>&1'
  echo "=== Phase 0 capture finished: $(date -Is) ==="
} >> "$WS/logs/phase0.log" 2>&1
echo "done"
