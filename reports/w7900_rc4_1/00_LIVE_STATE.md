# RC4.1 — Live state at mission start (M0 audit)

Captured 2026-11-22 22:49–23:00 UTC.

## Host

- hostname: j-7uqnwhrwmv2s44k6zdqzoq5idj
- OS/kernel: Ubuntu, Linux 6.8.0-79-generic x86_64, up 146 d
- user: root (uid 0)
- workspace disk: NFS-mounted /workspace 95% used (1.4 GiB free) —
  NOT used for GPU evidence (all heavy artifacts under /data)
- /data: overlay, 868 GiB free

## GPU (rocm-smi live)

- AMD Radeon PRO W7900D 48 GB, gfx1100, model 0x744b SKU D7070910,
  PCI 0000:03:00.0 (via torch props/sysfs), node id 2
- VRAM total 51,522,830,336 bytes = 47.98 GiB = 51.5 decimal GB
- VRAM used at start: 28,028,928 B (idle baseline)
- /dev/kfd present; /dev/dri/renderD128 present

## Stack

- ROCm 7.2.1 host interface; userspace wheels rocm7.14.1;
  torch 2.12.0+rocm7.14.1 (HIP 7.14.60850), Env A (yue2-torch) and
  Env B (yue2-gfx1100) venvs verified importable
- sglang: /data/yue2/upstream/sglang @ ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f
  (installed tree; git rev-parse of the tree)
- models: /data/yue2/models/YuE2-3B, YuE2-Vae-legacy

## Processes / GPU ownership at start

- no sglang/server/python generation processes running (only jupyter-lab,
  kernel zombies from Nov 16-19 sessions, and stale pytest stub servers
  under /tmp/pytest-of-root from Nov 19 — none owned by this mission,
  none touching the GPU per KFD table)
- /data/yue2/gpu.lock: not held
- No pkill/kill of any foreign process was performed during this mission.

## Git / GitHub

- repo /workspace/YuE2-SGLang-ROCm, branch mission/w7900-rc4-repro-reliability
  at 16f2504 (== origin, == PR #17 head), tree clean
- PR #17 OPEN/DRAFT (base mission/joint-blog-rc2), both cpu checks SUCCESS
  on 16f2504 (runs 45076549873 / 45076547844)
- PR #16 OPEN/DRAFT (head 48d1cb6, base integration/joint-blog-rc)
- gh auth: AIwork4me (push URL direct github.com; fetch via gh-proxy mirror)

## Mission-end recheck

- no project server processes remain; port 31000 free; VRAM 28,028,928 B
  (baseline); gpu.lock not held (receipts in phase logs)
