# Standalone PR draft: python-multipart runtime dependency (READY, NOT PUBLISHED)

Publication blocked on owner approval of final scope/description (mission rule).

- Fork branch: `AIwork4me/sglang-omni:fix/declare-python-multipart`
- Branch commit: **a5b78d7948fe11b388b22a2cb6609f76e39de510**
- Parent (base): sgl-project/sglang-omni main @ cba5a74f14e75b4fe80ed5079c1489c58b94f518
- Diff: 6 pyproject variants +1/-0 each (`"python-multipart>=0.0.20",` after the
  fastapi line) + tests/unit_test/test_packaging_multipart.py (+52).
- Six of seven blob SHAs are byte-identical to the previously reviewed local
  commit daf1a113 (pyproject.toml differs only because upstream main moved).
- Verified NOT a duplicate: no pyproject variant on upstream main declares
  python-multipart; no open PR/issue mentions it (Phase 1 search).
- Reproduction (isolated venv, fastapi 0.143.0 / starlette 1.8.0):
  `RuntimeError: Form data requires "python-multipart"` at route registration
  without the package; with 0.0.32 both regression tests pass.
- cpu/npu/xpu variants have no gradio — no transitive rescue there; main/rocm/
  musa carry gradio>=4.0.0 which usually (not always) pulls it transitively.
- No CUDA/ROCm dependency changes; no unrelated upgrades; isolated from
  YuE2 ROCm PR #1 (different repo target branch: upstream main, not add_yue2).

## Proposed PR

- Title: `fix(packaging): declare python-multipart runtime dependency`
- Target: `sgl-project/sglang-omni:main` (NOT the author's add_yue2)
- Head: `AIwork4me:fix/declare-python-multipart`

### Body

`sgl-omni serve` registers `POST /v1/audio/voices` (UploadFile/File/Form
parameters) unconditionally in `create_app -> register_voices`, and
`speech_to_text` declares further File/Form parameters. FastAPI raises
`Form data requires "python-multipart"` **at route registration** when the
package is absent — i.e. the server fails to start, on every platform
(CUDA/ROCm/CPU/NPU/XPU/MUSA alike).

python-multipart is currently not declared in any packaging target. Some
variants carry it transitively via `gradio>=4.0.0`, but `pyproject_cpu.toml`,
`pyproject_npu.toml` and `pyproject_xpu.toml` do not include gradio at all,
so those installs fail outright.

This PR declares it as a direct runtime dependency (floor `>=0.0.20`) in all
six pyproject variants that declare fastapi, and adds a focused regression
test asserting (a) a File/Form route registers at app startup and (b) every
pyproject variant declaring fastapi also declares python-multipart.

Reproduced in an isolated environment (fastapi 0.143.0, starlette 1.8.0):
without the package route registration raises; with 0.0.32 it succeeds.

Platform-neutral packaging fix; no runtime code changes.
