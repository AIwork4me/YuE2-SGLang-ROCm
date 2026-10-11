# ROCm Compatibility Patches (gfx1151)

Each patch is minimal, documented, and independently applicable on top of the
pinned SGLang PR #42106 checkout (`ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`).
Apply with `git apply patches/0001-0005-rocm-compat.patch` from the sglang
repository root. The series is a single file because the hunks are
independent per file; every hunk is described below.

## 0001 — quark/schemes/quark_w4a4_mxfp4.py: guard aiter imports

**Original behavior:** module-level `if _is_hip:` imports of `aiter.*`
(4 symbols) assume ROCm ⇒ aiter installed.
**Problem:** aiter ships only for Instinct CDNA (gfx94x/gfx95x); no gfx1151
build exists (AMD multi-arch index has none; PyPI `aiter` is an unrelated
2019 package). Import of the quantization chain — and therefore of any model,
including YuE2 — raises ModuleNotFoundError.
**Root cause:** "HIP implies aiter" platform assumption; upstream ROCm CI
only covers Instinct parts.
**Patch:** try/except ImportError binding the four names to `None` — exactly
the existing non-HIP fallback shape in the same file.
**Compatibility impact:** none on NVIDIA (guard under `_is_hip`); none on
Instinct (imports succeed unchanged).
**Accuracy risk:** zero for YuE2 (bf16, no Quark W4A4 layers). Without aiter
the registered custom ops fail at call time with a loud TypeError if a Quark
model is ever requested — better diagnosability than today's import crash.
**Test:** `tests/test_yue2_rocm_fallbacks.py::test_quantization_chain_imports`.

## 0002 — quark/schemes/quark_w4a4_mxfp4_moe.py: dynamic_mxfp4_quant → None without aiter

Same pattern; the file already had a `dynamic_mxfp4_quant = None` fallback for
non-HIP; the HIP branch now also falls back to None when aiter is absent.
**Test:** same as 0001.

## 0003 — quark_int4fp8_moe.py: guard shuffle_weight + ON_GFX950 probe

The `torch.cuda.get_device_properties("cuda").gcnArchName` probe also runs
under the guard, so a gfx1151 device (gcnArchName `gfx1151`) yields
`ON_GFX950=False` instead of an aiter import error.
**Test:** same as 0001.

## 0004 — yue2/fastpath.py + yue2/song.py: gate DeepSelect on actual kernel support

**Original behavior:** `fast_sampler_available()` = env flag ∧ backend module
importable ∧ `torch.cuda.is_available()`. The step-graph path in
`song.py` enters whenever `_load_topk_backend()` is non-None.
**Problem:** `sglang.kernels.ops.deep_select` is a *pure-Python wrapper* around
a CUDA-only JIT kernel (nvcc/cutlass, SM 9.0/10.0/10.3). On ROCm the wrapper
imports fine, `torch.cuda.is_available()` is True (HIP), so the FastSampler is
constructed and the step-graph path proceeds — then `topk()` raises
"DeepSelect does not support SM115" *at call time*, i.e. mid-decode or inside
CUDA-graph capture, killing the request instead of falling back.
**Root cause:** importability conflated with runnability; the tree's own
`is_deepselect_supported()` (which correctly returns False when
`torch.version.cuda is None` or capability ∉ {90,100,103}) is never consulted
on these two paths.
**Patch:** `fast_sampler_available()` and the step-graph gate now consult
`is_deepselect_supported()`; `batched.py::batched_ar_enabled()` consults
`fast_sampler_available()` (review follow-up). Unsupported devices fall back
to (a) the reference pure-torch sampler in `_decode_loop`, (b) the looped AR
path, and (c) per-request AR instead of batched-AR — all of which the PR
already ships as first-class code paths.
**Compatibility impact / accuracy risk:** none on supported CUDA GPUs (the
helper returns True there; behavior identical). On ROCm it selects the
documented reference implementations — no sampling math changes.
**Tests:** `test_deepselect_fallback`, plus the whole-suite green run
(`test_ar_graph_vs_eager_logits` exercises the surviving graph path).

## 0005 — yue2/fa3.py: fall through to native ATen flash when the shared wrapper fails

**Original behavior:** `varlen_attention()` calls SGLang's shared
`flash_attn_varlen_func` when `SGLANG_YUE2_FA3=1` (default); only when the
*import* fails does it call `torch.ops.aten._flash_attention_forward`.
**Problem:** on ROCm the shared wrapper imports but its kernels are CUDA-only;
at call time it tries `from flash_attn import flash_attn_varlen_func` (FA2
fallback) which is not installed → ModuleNotFoundError mid-forward. (Exactly
the failure mode the mission brief predicted for `SGLANG_YUE2_FA3=0`-style
gaps: the env flag does not guarantee a working path.)
**Patch:** wrap the shared-wrapper call in try/except Exception and fall
through to `torch.ops.aten._flash_attention_forward`.
**Validation on gfx1151** (torch 2.12.0+rocm7.14.1): the ATen op exists with
`seqused_k` in its schema, executes varlen + GQA + bf16 correctly, and matches
an fp32 hand-computed reference within bf16 noise (max|diff| ≈ 4e-3 over
kv-len 5/16 probes). `tests/test_yue2_rocm_fallbacks.py::
test_aten_flash_varlen_numerics` locks this in.
**Compatibility impact / accuracy risk:** none on CUDA (wrapper succeeds;
except never taken). On ROCm it activates a numerically validated PyTorch
native operator.

## Not patched (auto-fallbacks verified sufficient)

- `cuda_graph.py` `_decode_fused` (sgl_kernel): already behind a try/except
  ImportError → `use_fused_kernels=False`.
- `nar_fast.py`: `_sgl_kernel()` lazy loader returns None → the NAR stage
  catches `ValueError` and uses the reference `nar.synthesize` (pure torch).
- GraphAR attention `auto`: resolves to "flash" on ROCm (ATen op present),
  and HIP graph capture/replay is functional on gfx1151 (validated).
  The `cudnn` branch would fail on ROCm (SDPBackend.CUDNN_ATTENTION has no
  kernel) but is never auto-selected; the `sdpa` branch uses the MATH backend
  (correct; slower — Phase 9 optimization candidate).
- `batched.py` batched-AR (SGLANG_YUE2_BATCHED_AR): `batched_ar_enabled()` now
  also consults `fast_sampler_available()` (patch 0004 extension), so the
  BatchedGraphSampler path stays off on gfx1151 even with the flag unset;
  previously only the env flag gated it (correct via stage-level fallback, but
  noisy and wasteful).

## 0006 — wsb_metrics/wsb_eval.py: explicit ROCm torch-family environment override

**Original behavior:** `verify_environment` pins every package in
`configs/{metrics,eval}.installed.lock.txt` exactly (torch 2.9.1/2.7.0 CUDA,
torchaudio, torchvision, triton, vllm 0.14.0, …) and refuses any deviation.
**Problem:** those wheels are CUDA-only; AMD publishes no ROCm build of those
versions. On gfx1151 the evaluator cannot start at all ("Found no NVIDIA
driver").
**Patch:** under `WSB_ROCM_TORCH_OVERRIDE=1`, the torch-family quartet
(torch/torchaudio/torchvision/triton) is exempted from the equality check;
the environment receipt still records the ACTUAL versions plus a
`rocm_torch_override` marker, every other package must still match exactly,
and the Python 3.12.11 check remains mandatory. `release.json`'s hash for
`wsb_eval.py` is updated openly (integrity chain preserved, not bypassed).
Metric code, model weights, selection logic, aggregation: untouched.
**Environment delta:** metrics venv torch 2.9.1→2.10.0+rocm7.14.1
(torchvision 0.24.1→0.25.0, torchaudio 2.9.1→2.10.0, triton 3.5.1→3.6.0);
eval venv torch 2.7.0→2.10.0+rocm7.14.1 (torchvision 0.22.0→0.25.0).
Cross-vendor numerical equivalence cannot be verified on this host (no NVIDIA
GPU); the substitution is disclosed in evaluator_environment.json and every
affected summary, and SongBench outputs were sanity-banded against reference
ranges.

## 0007 — wsb_metrics/src/mot_infer/eval_worker.py: PER ASR via qwen_asr transformers backend on ROCm

**Original behavior:** PER runs Qwen3-ASR-1.7B through vLLM
(`Qwen3ASRModel.LLM(...)`, temperature 0, max_tokens from config) and records
per-chunk raw outputs (text / generated_tokens / finish_reason) by wrapping
the vLLM `generate`.
**Problem:** vLLM 0.14.0 has no ROCm build (PyPI `vllm-rocm` is 0.6.3/cp310,
2019-era); its platform detection fails on AMD ("Device string must not be
empty").
**Patch:** under the same `WSB_ROCM_TORCH_OVERRIDE=1` flag, the scorer builds
`Qwen3ASRModel.from_pretrained(...)` — the qwen_asr package's own
first-class transformers backend — with identical chunking, prompt building
and decoding (shared `transcribe()` code path) and greedy decoding (HF
generate default == temperature 0). The record shim is adapted to keep the
same receipt fields; `finish_reason` maps to `"length"` iff the continuation
hits the cap. Same model checkpoint, same processor, same 4-repeat protocol,
same phonemization/scoring code.
**Accuracy risk:** decode-level equivalence is expected (greedy, same
checkpoint/processor); batching differs (HF batching vs vLLM continuous
batching) which can change floating-point reduction order only.
