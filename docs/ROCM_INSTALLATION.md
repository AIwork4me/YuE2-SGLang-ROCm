# ROCm Installation Notes (gfx1100 / Radeon PRO W7900)

Machine-agnostic. Written from the verified W7900 installation
(`reports/gfx1100/PHASE0_PREFLIGHT.md`, `PHASE1_INSTALL.md`).

## Layered stack (what needs what)

| Layer | Source | Version on the verified rig | Notes |
|---|---|---|---|
| Kernel driver (amdgpu/ROCk) | host OS | 6.16.13 | **never modified** by this project |
| Host ROCm userspace | distro/AMD | 7.2.1 (`/opt/rocm`) | only used for `rocminfo`/`rocm-smi` tooling here |
| Python | python3.12 (venv) | 3.12.3 | 3.12.x; evaluator needs exactly 3.12.11 (it self-installs via uv) |
| torch stack | `repo.amd.com/rocm/whl-multi-arch` | 2.12.0+rocm7.14.1 family | venv-local userspace ships INSIDE the wheels (`_rocm_sdk_*`) |

## Key facts learned on this rig

1. **The AMD multi-arch wheels are self-contained.** Installing
   `torch[device-gfx1100]` also installs `rocm-sdk-core/libraries/device-gfx1100`
   (full 7.14.1 userspace incl. gfx1100 MIOpen kernels) into `site-packages`.
   `import torch` calls `torch._rocm_init.initialize()` which loads the venv
   userspace (verified by `/proc/self/maps`: 61 venv libs, **0** host `/opt/rocm`
   libs on the default path). You do NOT need a matching host userspace.
2. **Host vs wheel userspace mismatch is safe but document it.** Our host has
   7.2.1; wheels are 7.14.1. Kernel 6.16.13 >= userspace requirements, and the
   venv userspace wins load order. No `LD_LIBRARY_PATH` is set anywhere.
3. **pip index pinning.** Use `-i https://pypi.org/simple` (or your mirror) for
   general packages; the AMD index only for the torch family. Never let a
   resolver "fix" torch: guard with a constraints file
   (`torch==2.12.0+rocm7.14.1`, ...) so any conflict fails loudly.
4. **sgl-kernel / flashinfer / aiter**: no ROCm gfx1100 builds exist.
   - aiter: Instinct CDNA only (gfx94x/95x) — patches 0001-0003 guard imports.
   - sgl_kernel (PyPI): CUDA sm100 build; it even misreads gfx capability 11.0
     as "SM110". Do not install; patches/fallbacks handle absence (0008).
   - flashinfer: CUDA-only flavors; YuE2 does not need it on ROCm.

## Verbatim installation (the only blessed sequence)

```bash
python3.12 -m venv environments/yue2-gfx1100
source environments/yue2-gfx1100/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install \
  --index-url https://repo.amd.com/rocm/whl-multi-arch/ \
  "torch[device-gfx1100]==2.12.0+rocm7.14.1" \
  "torchvision[device-gfx1100]==0.27.0+rocm7.14.1" \
  "torchaudio==2.11.0+rocm7.14.1"
```

Validation (must all pass before proceeding):

```bash
python - <<'PY'
import torch, torchvision, torchaudio
assert torch.__version__ == "2.12.0+rocm7.14.1"
assert torchvision.__version__ == "0.27.0+rocm7.14.1"
assert torchaudio.__version__ == "2.11.0+rocm7.14.1"
assert torch.version.hip and not torch.version.cuda and torch.cuda.is_available()
assert "gfx1100" in torch.cuda.get_device_properties(0).gcnArchName
for dt in (torch.float32, torch.float16, torch.bfloat16):
    c = torch.randn(1024, 1024, device="cuda").to(dt) @ torch.randn(1024, 1024, device="cuda").to(dt)
    torch.cuda.synchronize(); assert torch.isfinite(c).all()
print("W7900 ROCm PyTorch smoke test PASS")
PY
```

(ROCm PyTorch deliberately exposes the `torch.cuda` API — `torch.cuda` does NOT
imply NVIDIA here.)

## Proxy-constrained networks (findings from this rig)

- api.github.com + codeload.github.com + pypi.org + repo.amd.com + hf-mirror:
  reliable. github.com git-over-HTTPS and release assets (objects.githubusercontent):
  intermittent/blocked — use plain-HTTP git transport (`http://github.com/...`
  with a credential helper) or the GitHub REST API (`scripts/api_git.py`).
- Python 3.12.11 for the WSB evaluator downloads from GitHub releases; if that
  fails, build from python.org source into uv's managed directory
  (`docs/TROUBLESHOOTING.md` §python-3.12.11).
