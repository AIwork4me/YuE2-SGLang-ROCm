# Troubleshooting (AMD ROCm)

Historical campaign issues (2026-10, preserved from the gfx1100/gfx1151 campaigns) follow the new entries.

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


---

# New entries (2026-11 publication-readiness mission)

Real issues encountered on W7900-class hosts, with verified fixes. Each entry
names the exact symptom string where applicable.

## Generation / pipeline

### `RuntimeError: [ROCm] mha_varlen_fwd: seqused_k must be nullopt`
- **Where:** official `yue2-infer` (0.1.x) `--backend torch` (graph capture) on ROCm.
- **Cause:** GraphAR's attention-backend probe checks whether the aten
  `_flash_attention_forward` schema mentions `seqused_k` (it does on ROCm
  builds) and selects the varlen FlashAttention path, but the HIP kernel does
  not implement `seqused_k`.
- **Fix:** use `--backend torch-eager` (official CLI choice; public-SDPA path
  documented for AMD in YuE `docs/hardware.md`). No model-math change.
- **Upstream note:** a runtime capability probe (tiny 4-token probe call
  before selecting `flash`) would fix dispatch properly; patch prepared for
  owner-approved upstream submission.

### Empty ASR transcripts containing only `language None<asr_text>`
- **Where:** WSB PER evaluator (Qwen3-ASR) on some candidates.
- **Known behavior:** the ASR model emits no text for 4/4 repeats; the
  candidate scores PER 1.0. Historical campaigns retained and disclosed these
  (never excluded). See `patches/EVALUATOR_PATCH_AUDIT.md`.

## Installation

### `pip install -e` suddenly downloads CUDA torch (`torch==2.x.x` + `nvidia-*` wheels)
- **Cause:** pip build isolation fetches the package's build requirements,
  which pin CUDA torch; `--no-deps` does NOT cover the isolated build env.
- **Fix:** `pip install --no-deps --no-build-isolation -e <src>` (see
  `scripts/setup_sglang_gfx1100.sh`). Always re-verify
  `torch.version.hip is not None and torch.cuda.is_available()` afterwards.

### `OSError: [Errno 28] No space left on device` during pip/uv installs
- **Cause:** `/tmp` is a small tmpfs (4 GB) on lab containers; wheel builds
  need multi-GB.
- **Fix:** `TMPDIR=/data/<big-volume>/tmp` for every install command.

### `HIP error: device kernel image is invalid` (hipErrorInvalidImage)
- **Cause:** plain `torch==…+rocm…` wheels from the multi-arch index without
  the **device extra** — the default wheel set may exclude gfx1100 kernels.
- **Fix:** install `torch[device-gfx1100]==…+rocm…` (same for
  torchvision/torchaudio where extras exist). Verify with a small GPU matmul
  immediately after install.

### Proxy `CONNECT tunnel failed, response 503` on large downloads / git push
- **Cause:** site egress proxy intermittency for large CDN responses.
- **Fix:** retry (git pushes, asset downloads); for HF assets prefer
  `huggingface_hub` (resume+chunked) — see `scripts/fetch_eval_assets_hub.py`
  for the pinned-asset contract. Never switch to plain HTTP.

### `raw.githubusercontent.com` unreachable but github.com works
- **Cause:** egress allowlist granularity.
- **Fix:** use `git clone` or the GitHub contents API instead of raw URLs.

## Campaign harness

### Every candidate logs `finalize_failed` with an empty error, but manual finalize succeeds
- **Cause:** the driver's completion check inserts only the historical
  `$WS/benchmark/wsb_metrics` path; on layouts where the evaluator tree is at
  `benchmark/WildSongBench/evaluation/wsb_metrics`, its
  `from artifact_storage import verify_result` fails silently.
- **Fix (this repo):** `candidate_complete` now probes all known layouts and
  logs failures under `YUE2_DRIVER_DEBUG_LOG`. Machine-side alternative:
  `ln -s <real-wsb_metrics> $WS/benchmark/wsb_metrics`.
- **Recovery:** re-verify bundles with the official `verify_result` and mark
  journal rows `complete(recovered)` (documented; historical precedent).

### Driver refuses resume: `run_config.json exists with different identity`
- **Cause:** run identity is write-once; `--run-id` differs (or stack pins changed).
- **Fix:** pass the SAME `--run-id` on resume. If pins genuinely changed, that
  must be a NEW run directory (by design).

## Serving (SGLang)

### Server healthy but requests queue instead of parallelizing
- **Expected:** the validated configuration runs one generation at a time
  (correctness-first ROCm flag matrix). Client concurrency = queueing, not
  GPU parallelism. Never report queued clients as parallel throughput.

### MIOpen `IsEnoughWorkspace ... GemmFwdRest` warnings during NAR
- **Benign:** solver workspace probing noise; generation proceeds normally.
