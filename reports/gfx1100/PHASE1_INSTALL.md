# PHASE 1 — Exact PyTorch / ROCm 7.14.1 Installation (gfx1100)

**Status: PASS (GATE 1 met)** · Date: 2026-10-11
**Evidence:** `evidence/gfx1100/phase1_validation.log`, `evidence/gfx1100/phase1_torch_environment.json`
**Reproducer:** `scripts/setup_gfx1100_rocm7141.sh` (idempotent; exact command embedded), `scripts/validate_torch_gfx1100.sh`

## 1. Installation

Fresh Python 3.12 venv (`environments/yue2-gfx1100`), then the mission-mandated
command, unchanged:

```
python -m pip install \
  --index-url https://repo.amd.com/rocm/whl-multi-arch/ \
  "torch[device-gfx1100]==2.12.0+rocm7.14.1" \
  "torchvision[device-gfx1100]==0.27.0+rocm7.14.1" \
  "torchaudio==2.11.0+rocm7.14.1"
```

## 2. Mandatory validation (exact mission script) — PASS

| Check | Result |
|---|---|
| torch / torchvision / torchaudio | `2.12.0+rocm7.14.1` / `0.27.0+rocm7.14.1` / `2.11.0+rocm7.14.1` |
| `torch.version.hip` / `torch.version.cuda` | `7.14.60850` / `None` |
| `torch.cuda.is_available()` | True (HIP maps to the torch.cuda API) |
| Device | `AMD Radeon Pro W7900D`, `gcnArchName='gfx1100'`, 49136 MB, L2 6 MB, PCI 195 (0xc3) |
| FP32 / FP16 / BF16 GEMM 1024² | all finite, `PASS` each |
| W7900 smoke test | **PASS** |

Note: the device reports as "W7900**D**" — the China-market SKU of the same
gfx1100 48 GB silicon (PCI ID identical, `1002:744b`); recorded for honesty.

## 3. Extended validation — PASS

- allocator tracking (`memory_allocated` before/after 32 MiB tensor): OK
- `torch.cuda.synchronize()` semantics: OK
- peak-memory stats after 2048² GEMM: `138,023,936` bytes tracked: OK
- H2D/D2H round-trip of 1M float64: bit-identical (`torch.equal`): OK
- 50 consecutive small kernel launches on default stream: correct accumulation,
  39.5 ms total (per-launch ≈ 0.8 ms, launch-path healthy): OK
- cudnn (MIOpen-backed) available: True

## 4. ROCm userspace provenance (mission-required verification)

The wheels installed a **venv-local ROCm 7.14.1 userspace**
(`rocm-sdk-core`, `rocm-sdk-libraries`, `rocm-sdk-device-gfx1100`,
`rocm-bootstrap`) under `site-packages/_rocm_sdk_*/lib`. Host `/opt/rocm` is
7.2.1.

**Runtime behavior (authoritative, verified by process-maps inspection and
independently re-verified under `env -i` in reviews/gfx1100/PHASE1_REVIEW.md):**
torch ships a `_rocm_init` module that calls the ROCm runtime-wheel
initialization during `import torch` itself (see the comment block in
`torch/__init__.py`, referencing AMD's TheRock python-packaging design).
Consequently a plain `import torch` already maps the venv 7.14.1 userspace
(rocBLAS, hipBLAS, MIOpen incl. gfx1100 kernels, HSA runtime) into the process.
The earlier "25 host /opt/rocm libraries" figure in the first draft of this
report was a static `ldd`-resolution artifact, **not** the runtime state.

Residual host interactions: the container presets
`LD_LIBRARY_PATH=/opt/rocm/lib:/usr/local/lib:`; a handful of non-compute
profiling libs (e.g. `libhsa-amd-aqlprofile64`) may resolve from the host. No
compute path depends on host 7.2.1 libraries; all GEMM/attention kernels map
from the venv. An explicit `import rocm_sdk; rocm_sdk.initialize_process()`
before torch is harmless but redundant with `_rocm_init`. **No script in this
repository sets or modifies `LD_LIBRARY_PATH`.**

## 5. Wheel provenance

`pip freeze` captured in `evidence/gfx1100/phase1_validation.log`; full freeze
also at `logs/phase1_pip_freeze.txt`. Key packages:
`amd-torch-device-gfx1100 2.12.0+rocm7.14.1`, `rocm-sdk-core/libraries/device-gfx1100 7.14.1`,
`triton 3.8.0+git4cff872c.rocm7.14.1`, `numpy 2.4.4`, `pillow 12.2.0`.
No CUDA-metapackages, no nvidia-* wheels, no flashinfer (verified by freeze
inspection). The venv now holds the golden reference set; all later dependency
installs use `--no-deps` or constraint pins that protect torch.

## 6. Gate 1 verdict

- All required versions installed **exactly**: PASS
- GPU computation actually succeeds (3 dtypes + extended): PASS
- No CUDA PyTorch substitutions: PASS (freeze audited)
