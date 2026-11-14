# 00 ENVIRONMENT — Fresh W7900 Image (mission/w7900-fresh-image-final-closure)

Captured: 2026-11-14T23:52Z (first minutes of the fresh image; machine-readable twin: `00_ENVIRONMENT.json`)

## Verdict

**Fresh image confirmed and healthy.** All P0 checks passed on physical hardware.
No prior mission state exists on this image (`/data` empty, `/workspace` only held tooling).

## Hardware

| Item | Value |
|---|---|
| GPU exposed to container | 1× AMD `gfx1100`, PCI `0000:03:00.0`, DID `0x744b` (Navi 31, W7900-class) |
| VRAM | 51,522,830,336 B = **47.98 GiB** |
| GPU UUID | `GPU-3d1e08ee04727918` |
| Host chassis | 8× identical `0x744b` cards physically present; container cgroup exposes exactly **one** — consistent with the mission's single-GPU contract |
| CPU | AMD EPYC 9334 32-Core Processor (128 logical CPUs visible) |
| RAM | 503 GiB host; **cgroup ceiling 55 GiB** (`memory.max` = 59,055,800,320 B) |
| OS | Ubuntu 24.04.4 LTS, kernel 6.8.0-79-generic |
| Disk | `/` overlay 3.5T (1.6T free) → `/data` created here; `/workspace` loop 98G (93G free); **`/tmp` is a 4G tmpfs — never used for benchmark data** |

## ROCm stack (preinstalled — preserved unmodified per P0.1)

| Component | Version |
|---|---|
| Kernel driver | amdgpu **6.16.13** |
| ROCm userspace | **7.2.1** (`/opt/rocm-7.2.1`) |
| HIP runtime | 1.18 · hipcc reports HIP 7.2.53211-e1a6bc5663 |

The frozen experiment stacks (torch `2.10.0+rocm7.1`, torch `2.12.0+rocm7.14.1`
with `[device-gfx1100]` extras) install their own ROCm userspace subsets into
their venvs; the 6.16.13 kernel driver is newer than every frozen pin, which is
the supported compatibility direction. Verified in Phase P2 by per-environment
GPU smoke tests — not assumed.

## Network

Egress via lab proxy (`HTTP(S)_PROXY=notebook-egress-proxy…:3128`). Verified
HTTP 200: github.com, huggingface.co, pypi.org, download.pytorch.org.
Intermittent 503s expected (handoff gotcha 5) — all fetchers use retries, HTTPS only.

## GPU smoke test (P0.2) — see `00_GPU_SMOKE.json`

Executed with the base-image venv torch 2.9.1+git (ROCm) before any installation:

- `torch.cuda.is_available()` = **True** (HIP build; `torch.version.hip` = 7.2.53211)
- Device: `gfx1100`, 48 GB — matches expected hardware
- BF16 matmul 4096³: ~13.0 ms (≈21 TFLOPS — healthy for W7900-class bf16)
- FP32 matmul 2048³ vs CPU reference: max rel err **2.2e-06**
- SDPA (MATH + default backend): finite, max diff 0.002 (bf16-expected)
- Alloc 4 GiB / release: memory returned correctly
- Sync & error paths: OK

**Integrity note:** the first smoke run reported two check failures that were
bugs in the test itself (wrong reference math for the corner-block comparison;
wrong byte-count threshold vs allocated bytes). The test was corrected — not
weakened — and re-run; corrected assertions pass. First-run JSON preserved at
`/data/yue2/logs/gpu_smoke_p02_stderr.log` context in the run log; this is
disclosed rather than hidden.

## Python

- System `python3` = 3.12.3; `/opt/venv` base image venv (torch 2.9.1 ROCm git
  build, transformers 4.57.6, vllm 0.16.1.dev rocm721) — used **only** for P0.2
  hardware validation. The three mission environments are built isolated in
  Phase P2 and never share the base venv.

## Storage plan — see `00_STORAGE_PLAN.md`

`/data/yue2` (models, hf-cache, environments, upstream, benchmark, logs, tmp)
and `/data/yue2-runs` on the 1.6T-free root overlay; `TMPDIR=/data/yue2/tmp`
everywhere.
