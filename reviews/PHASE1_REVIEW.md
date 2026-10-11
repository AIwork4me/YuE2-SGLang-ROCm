# PHASE 1 Independent Review — ROCm 7.14.1 Environment (gfx1151)

**Reviewer:** Independent Verification Subagent
**Date:** 2026-10-11
**Verdict: PASS**

All substantive claims re-verified against real artifacts and by independent
re-execution in `environments/yue2`. No claim failed verification. One P2
evidence-trail gap and several P3 notes below; none block Phase 2/3.

## 1. Artifacts audited

| Artifact | Result |
|---|---|
| `scripts/setup_gfx1151.sh` | Coherent; matches logged behavior (incl. the cargo-failure iteration that motivated `SGLANG_BUILD_RUST_EXTS=none`); torch-install step idempotent |
| `evidence/dependency_matrix.json` | All checkable claims verified (see §3) |
| `reports/PHASE1_INSTALLATION.md` | All checkable claims verified (see §3); one evidence gap (P2-1) |
| `patches/0001-0003-aiter-import-guards.patch`, `patches/README.md` | Patch is **byte-for-byte identical** to `git -C upstream/sglang diff` (`diff -u` clean) |
| `logs/phase1.log`, `logs/phase1_pipfreeze.txt`, `logs/model_hash_check.txt` | Read in full; see P2-1 / P3-1 |
| `upstream/sglang` working tree | Audited directly (git status/diff/log) |

## 2. Independent re-execution results (venv `environments/yue2`)

| Check | Claimed | Observed | Match |
|---|---|---|---|
| torch / HIP / device | 2.12.0+rocm7.14.1, hip 7.14.60850, AMD Radeon 8060S | `2.12.0+rocm7.14.1 7.14.60850 AMD Radeon 8060S Graphics` | Yes |
| BF16 GPU matmul | finite | finite, checksum −21175.6191; rel err vs fp32 reference 9.11e-05 (added correctness cross-check, not just finiteness) | Yes |
| `from sglang.srt.models.yue2 import modeling_yue2, modeling_vae; from sglang.multimodal_gen.runtime.pipelines import yue2_pipeline` | OK | `OK` (with the expected pre-existing upstream warning `aiter MXFP4 kernels not available`, emitted by *unmodified* `multimodal_gen/runtime/layers/quantization/mxfp4.py`) | Yes |
| `uv pip check` | 17 incompatibilities, all attributable to documented CUDA-only exclusions | Exactly 17; each one maps 1:1 to the matrix's `deliberately_not_installed` list or the documented `torch==2.14.1`-vs-ROCm conflict; no ROCm-relevant conflict | Yes |
| sglang install | 0.0.0.dev1+gced0ef7d1, editable from checkout | `sglang.__file__` → `/home/amd/Desktop/YuE2/upstream/sglang/python/sglang/__init__.py`; version matches | Yes |

## 3. Specific claim verifications

**Model artifact SHA-256s** (computed myself with `sha256sum`):

| File | Expected | Observed |
|---|---|---|
| `models/YuE2-3B/model.safetensors` | `1d55c42c…e59e9` | `1d55c42c1a9875c34f5d736e15078449992b044e807ce2a138e6cf289a1e59e9` — match |
| `models/YuE2-Vae-legacy/model.safetensors` | `b6d28362…5044` | `b6d283628913bb41145ba99e2314eef613905ee95f690eb70e8212d5f4965044` — match |
| `models/YuE2-3B/yue2_infer-0.1.3-py3-none-any.whl` | `156d6b8b…4f07` | `156d6b8b7e46c3bd23cf22a50d3c20c403e5dc7f4a315582a224a840b01f4f07` — match |

All three also match `logs/model_hash_check.txt`.

**Git state of `upstream/sglang`:**
- `rev-parse HEAD` = `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` — exact match to the pin.
- `git status --porcelain`: exactly 3 modified files (the three quark/quant files), 0 untracked.
- `git diff` is byte-for-byte identical to `patches/0001-0003-aiter-import-guards.patch`.
- Detached HEAD at the PR head commit; origin `sgl-project/sglang` (see P3-3).

**Patch content audit (read line by line):** every changed line lives inside an
`if _is_hip:` block and only wraps aiter imports in `try/except ImportError`
binding the prior names to `None`, plus comments. **No changes to sampling
math, model architecture, tokenizers, or seeds** — the diff touches only
import statements (identical statements on the success path) in three
quantization-scheme modules. It mirrors the pre-existing upstream guard
pattern in `multimodal_gen/runtime/layers/quantization/mxfp4.py` (verified
unmodified), and downstream code already handles the `None` symbols
(`dynamic_mxfp4_quant is None` checks at quark_w4a4_mxfp4_moe.py:571,738).

**NVIDIA/Instinct no-op claim: verified by code inspection.**
- NVIDIA: `is_hip()` is False, so none of the changed lines ever execute — the patch changes no code path that runs on CUDA.
- Instinct ROCm (aiter installed): the `try` succeeds; the wrapped import statements are byte-identical to the originals, including the `ON_GFX950` probe (same statement, same order). Behavior identical.

**aiter availability claims:**
- `curl -s --max-time 15 https://repo.amd.com/rocm/whl-multi-arch/ | grep -i aiter` → no match; page verified non-empty (57 torch-related lines), so the negative is meaningful. Claim confirmed.
- PyPI `aiter` (via pypi.org JSON API): v0.13.20191203 (2019-12-04), "useful patterns building upon asynchronous iterators" by Richard Kiss — unrelated to AMD's AITer. Claim confirmed.

**Dependency curation vs upstream `pyproject.toml`:** every upstream dependency
is either installed by the script, in the documented exclusion list (16
CUDA-only packages), excluded by platform marker (`av`, `decord2` aarch64-only;
`tomli` py<3.11), or is torch/vision/audio (replaced by ROCm stack per mission
rule 7). Extras `imageio`, `imageio-ffmpeg`, `diffusers`, `addict`,
`cache_dit` are documented in the report. `diffusers==0.37.0` pin (pyproject
line 118) vs installed 0.41.0 is recorded in the matrix, not silent. `uv pip
check` output confirms `sglang-kernel==0.4.9` metadata pin (drift vs PR prose
0.4.7 correctly noted) and `torchaudio==2.11.0` matching upstream exactly.

## 4. Issues

| ID | Severity | Issue |
|---|---|---|
| P2-1 | P2 | `logs/phase1.log` contains **no successful end-to-end script run**. The last recorded run (18:52:34) aborts in step 5 at `ModuleNotFoundError: No module named 'aiter'` (pre-patch); under `set -euo pipefail` the script then exits, so the log has no pip-check output and no `=== finished ===` marker. The report §2 "Verification results" and the matrix `verification` block are true of the *current* environment (this review re-proved every line) but are not evidenced by the log artifact itself. Fix: re-run `scripts/setup_gfx1151.sh` once post-patch and let the appended log capture the green run. |
| P3-1 | P3 | `logs/phase1_pipfreeze.txt` is a curated subset with `<not installed>` placeholders, not a full `uv pip freeze`. For byte-exact reproduction archive a complete freeze alongside it. |
| P3-2 | P3 | Device string truncated in report/matrix: actual `torch.cuda.get_device_name(0)` is `AMD Radeon 8060S Graphics`, artifacts say `AMD Radeon 8060S`. Cosmetic. |
| P3-3 | P3 | Matrix `install_source` says "branch add_yue2"; the checkout is a detached HEAD at the PR-head commit (no local branch). The commit pin — which is what matters — matches exactly. Wording nit. |
| P3-4 | P3 | On gfx1151 without aiter, `quark_int4fp8_moe.py::process_weights_after_loading` calls `shuffle_weight(...)` unguarded → would raise at weight-load for a Quark-int4fp8 MoE model (loud failure, not silent corruption), and the `not ON_GFX950` scale-halving branch becomes reachable on gfx1151. Zero impact on YuE2 (bf16, no Quark layers); squarely in Phase 3's declared fallback-validation scope. Recorded for Phase 3. |
| P3-5 | P3 | Setup script exports deprecated `HF_HUB_ENABLE_HF_TRANSFER=1` → FutureWarning in log; use `HF_XET_HIGH_PERFORMANCE` when convenient. |

No P0 or P1 issues found.

## 5. Verdict

**PASS.** Environment reproduces: pinned torch ROCm stack live-verified on the
gfx1151 device, BF16 GPU compute finite and fp32-consistent, full YuE2 import
chain green, all three model artifacts hash-exact, sglang checkout pinned at
the exact commit with the only working-tree change being the three verified
no-op-on-NVIDIA/Instinct aiter import guards (byte-identical to the archived
patch), and all 17 pip-check incompatibilities attributed to documented
exclusions. P2-1 is an evidence-archival gap, not a correctness gap.
