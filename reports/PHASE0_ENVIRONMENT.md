# PHASE 0 — Environment and Baseline Capture

**Status: PASS (GPU gate satisfied)**
**Date: 2026-10-11**
**Workspace: /home/amd/Desktop/YuE2**

## 1. Host summary

| Item | Value |
|---|---|
| CPU | AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S (Strix Halo APU), 32 threads |
| GPU | AMD Radeon 8060S (integrated), **gfx1151** confirmed via `rocminfo` (`amdgcn-amd-amdhsa--gfx1151`) |
| Dedicated VRAM (BIOS carveout) | 32.0 GiB (`/sys/class/drm/card1/device/mem_info_vram_total` = 34,359,738,368) |
| PyTorch-visible GPU memory | 100.0 GiB (GTT unified-memory pool) — *not* dedicated VRAM; over-allocation spills to system RAM |
| System RAM | 94 GiB total, ~87–90 GiB available at capture |
| Swap | 8 GiB (/swap.img, unused at capture) |
| OS | Ubuntu 24.04.4 LTS (noble) |
| Kernel | 6.17.0-1033-oem (in-tree `amdgpu`/KFD; no amdgpu-dkms) |
| Host ROCm userspace | 7.2.1 (`/opt/rocm-7.2.1`, rocm-core 7.2.1.70201) |
| Disk | 1.9 TB NVMe, 262 GB free at capture (86% used) — budgeted, monitored |
| Python | 3.12.3 system; mission venv `environments/yue2` via uv |

The host kernel driver was **not modified** (mission rule 8). The ROCm 7.14.1
userspace stack arrives bundled inside the AMD PyTorch wheels from
`repo.amd.com/rocm/whl-multi-arch`, coexisting with the host's 7.2.1 install.

## 2. Network posture (material constraint, shapes the whole mission)

| Endpoint | Status |
|---|---|
| huggingface.co | **UNREACHABLE** (TCP connect timeout) |
| hf-mirror.com | Reachable — all HF downloads use `HF_ENDPOINT=https://hf-mirror.com` |
| github.com | Intermittent — small `gh api` calls succeed with retries; large clones fail (TLS resets); shallow single-commit fetches succeed |
| repo.amd.com | Reachable (fast) |
| pypi.org | Reachable (slow) |

GitHub flakiness forced a shallow-fetch strategy for source checkouts
(documented in Phase 2). This is recorded as an environmental constraint, not a
code change.

## 3. GPU smoke test (Phase 0 gate)

Executed `scripts/phase0_gpu_smoke.py` with torch 2.12.0+rocm7.14.1
(`torch.version.hip = 7.14.60850`), device `AMD Radeon 8060S Graphics`,
capability (11,5):

| Precision | matmul 1024×1024 | finite | max abs diff vs fp32 |
|---|---|---|---|
| fp32 | OK | yes | 0 |
| fp16 | OK | yes | 4.9e-4 |
| bf16 | OK | yes | 3.9e-3 |

Result: `SMOKE_RESULT: PASS` (logs/phase0_gpu_smoke.log, .json).
`torch.cuda.is_available() == True`; device count 1.

## 4. Tooling

- git 2.43.0; gh CLI authenticated as **AIwork4me** (scopes: gist, read:org,
  repo, workflow) — sufficient to create the evidence repository.
- uv 0.12.3 for isolated environments.
- Target evidence repo `AIwork4me/YuE2-SGLang-ROCm` did not exist at capture;
  creation is authorized by the mission.

## 5. Memory/OOM risk assessment

Unified-memory APU: 32 GiB dedicated + GTT. YuE2-3B (≈3 B params, bf16 ≈ 6–8 GB
weights) plus KV/graph state fits dedicated VRAM comfortably *per stage*; the
main risks are (a) CUDA-graph-like HIP graph pools, (b) NAR/VAE peak buffers
during 9000-token generations, (c) evaluator models (SongBench/MuLan/
AllMusicCaps/PER) which are separate processes run after generation. The 8 GiB
swap and ~87 GiB free system RAM give headroom; generation runs will monitor
`amd-smi`/`free` continuously (Phase 6 reliability engineering).

## 6. Deviations from mission text

- Mission suggests ROCm 7.14.1 host toolchain; host userspace remains 7.2.1.
  PyTorch wheels bundle ROCm 7.14.1 userspace libraries, so the compute stack
  *is* 7.14.1 as required. No host driver/userspace changes made.
- `torch==2.12.0+rocm7.14.1` matched the mission pin exactly (verified against
  the AMD index before install).

## 7. Deliverables

- `evidence/environment.json` (machine-readable capture)
- `logs/phase0.log`, `logs/phase0_raw/*` (workspace, outside git)
- `scripts/collect_system_info.sh`, `scripts/phase0_gpu_smoke.py`
- `reviews/PHASE0_REVIEW.md` (independent subagent verdict)

## 8. Gate

**PASS** — GPU executes FP32/FP16/BF16 PyTorch ops with correct numerics;
environment report complete.
