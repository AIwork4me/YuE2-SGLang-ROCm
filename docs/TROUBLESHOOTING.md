# Troubleshooting (ROCm / YuE2 / SGLang / WSB on AMD)

Real issues hit on the gfx1100 rig, with root causes and fixes.

## Environment

**`ModuleNotFoundError: aiter`** when importing sglang models
→ patches 0001-0003 (aiter ships only for Instinct CDNA; imports guarded).

**`ImportError: ... common_ops ... sgl_kernel`** on `sglang serve` import
→ you installed PyPI `sgl-kernel` (CUDA sm100). Uninstall it. Absence is the
supported state on ROCm (patch 0008 guards the last unguarded imports).

**pip pulls CUDA torch 2.14.1 into sglang build**
→ `build-system.requires` pins CUDA torch; install with
`--no-build-isolation --no-deps` (quickstart step 3).

**`libnvrtc.so.12` errors**
→ a CUDA-only package sneaked in (sgl-kernel / flashinfer / nvidia-*).
`pip freeze | grep -Ei 'nvidia|cuda|sgl-kernel|flashinfer'` must be empty.

**Mixed host/wheel ROCm userspace worries**
→ don't set `LD_LIBRARY_PATH`. The wheels ship their own userspace and
`import torch` activates it (`torch._rocm_init`). Inspect with
`/proc/self/maps` (see `evidence/gfx1100/phase1_torch_environment.json`).

## Networking (egress-filtered hosts)

**git clone/push to github.com fails (CONNECT timeout)**
→ use plain-HTTP transport: `git config --global --add
url."http://github.com/".insteadOf "https://github.com/"` + an http-scope
credential helper; or `scripts/api_git.py` (full sync via REST API).

**HuggingFace timeouts**
→ set `HF_ENDPOINT=https://hf-mirror.com`; all pinned downloads are
SHA256-verified regardless of endpoint.

**uv / evaluator cannot fetch Python 3.12.11 (GitHub release asset blocked)**
→ build from python.org (reachable on our rig) into uv's directory:
```bash
curl -LO https://www.python.org/ftp/python/3.12.11/Python-3.12.11.tgz
tar xzf Python-3.12.11.tgz && cd Python-3.12.11
UVD=/root/.local/share/uv/python/cpython-3.12.11+20250918-x86_64-unknown-linux-gnu-install_only_stripped
./configure --prefix="$UVD/python" && make -j$(nproc) && make install
```

## Serving / generation

**503 / connection refused after long idle** — restart the launcher; the
driver (`run_wsb.py --max-retries`) retries transient failures and resumes
from verified candidates.

**`peak_memory_mb: 0.0` in HTTP responses** — known ROCm gap (nvidia-smi
probe). Use rocm-smi / server log stage timings (documented in
PHASE5_FIRST_AUDIO.md §5).

**Background jobs die when your shell exits** — launch with
`setsid nohup ... < /dev/null &` (plain `nohup &` was insufficient on our
orchestration shell; diagnosed in PHASE0 §3.4).

**Relative `--runs` paths corrupt run accounting** — driver now absolutizes;
always pass absolute paths anyway.

## Harness

**Validator says PILOT-INCOMPLETE with "unexpected candidate dir"**
→ pre-fix bug flagging `.wav` byproducts; fixed (directories only). Update
your checkout.

**"FATAL: run_config.json exists with different identity"**
→ intentional: never mix runs. Use a fresh `--runs` directory per run_id.

**Disk floor triggered (`skipped(disk)`)**
→ free space or raise `YUE2_MIN_FREE_GB`; use `--wav-archive` on large storage.
