# PHASE 3 Independent Verification Review — ROCm Compatibility RCA

**Verdict: PASS**

- Reviewer: independent verification subagent (no modifications except this file)
- Date: 2026-10-11
- Subject: `evidence/YuE2-SGLang-ROCm/reports/PHASE3_ROCM_RCA.md`, `patches/0001-0005-rocm-compat.patch`, `tests/test_yue2_rocm_fallbacks.py`, `evidence/compatibility_tests.json`, live tree `upstream/sglang` @ `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`

## 1. Independent verifications performed

### 1.1 Full test suite re-run — 10/10 PASS

Command: `source environments/yue2/bin/activate && python -m pytest tests/test_yue2_rocm_fallbacks.py -v`

Run three times (identical outcomes): **10 passed**, totals 27.89 s / 27.87 s / 27.81 s.
No `conftest.py` exists and no `SGLANG_*` env vars are set in the shell, so the suite
runs with default flags (i.e., the patches, not the launcher flag matrix, make it green).

Per-test durations (pytest `--durations=0`, third run):

| Test | Result | Duration |
|---|---|---|
| test_quantization_chain_imports | PASS | 2.84 s |
| test_deepselect_fallback | PASS | < 0.005 s |
| test_aten_flash_varlen_numerics | PASS | 0.33 s |
| test_masked_sdpa_math_fallback | PASS | 0.04 s |
| test_hip_graph_capture_replay | PASS | 0.04 s |
| test_model_loads_on_gfx1151 | PASS | < 0.005 s (module fixture setup: 4.21 s) |
| test_ar_graph_vs_eager_logits | PASS | 0.60 s |
| test_reference_sampler_distribution_matches_fastpath_semantics | PASS | 0.27 s |
| test_nar_solver_finite | PASS | 0.28 s |
| test_vae_decode_finite | PASS | 18.14 s |

The `test_ar_graph_vs_eager_logits` diagnostic print confirms: `backend=flash
prefill_max|diff|=0.0000 step_max|diff|=0.0000 logit_scale=33.75` (i.e., < 5e-5
against the 0.05 × scale tolerance).

### 1.2 Live diff vs patch file — IDENTICAL

`git -C upstream/sglang diff` is **byte-identical** to
`evidence/YuE2-SGLang-ROCm/patches/0001-0005-rocm-compat.patch` (`diff` → no
differences; `git status --porcelain` shows exactly 6 modified files, 0
untracked/staged). HEAD is the pinned PR commit `ced0ef7`. Diff stat: 6 files,
+66/−15, matching the report §3.

### 1.3 Hunk semantic audit — SAFE

Changed files are exactly the claimed set:
- `python/sglang/srt/layers/quantization/quark/schemes/quark_w4a4_mxfp4.py` (0001)
- `python/sglang/srt/layers/quantization/quark/schemes/quark_w4a4_mxfp4_moe.py` (0002)
- `python/sglang/srt/layers/quantization/quark_int4fp8_moe.py` (0003)
- `python/sglang/srt/models/yue2/fastpath.py` (0004a)
- `python/sglang/srt/models/yue2/song.py` (0004b)
- `python/sglang/srt/models/yue2/fa3.py` (0005)

`sampling.py` and `protocol.py` are **byte-identical to git HEAD** (`git diff
--name-only` does not list them; `git show HEAD:… | cmp -` clean). No changes to
sampling math (`distribution`/`window_penalty`/`_decode_loop` untouched), no
tokenizer changes, no seed changes, no ODE changes, no weight-loading changes
(`yue2_loader.py` untouched).

Per-hunk findings:
- **0001–0003**: try/except ImportError binding aiter names to `None`, exactly
  mirroring each file's own non-HIP fallback. `dynamic_mxfp4_quant = None` is
  explicitly handled downstream (`quark_w4a4_mxfp4_moe.py:571` raises
  `NotImplementedError`). Zero effect on YuE2 (bf16, no Quark layers).
- **0004a** (`fastpath.py:56-67`): `fast_sampler_available()` now consults
  `is_deepselect_supported()`; import failure still returns False via the
  existing `except Exception`. Both looped-path call sites
  (`sampling.py:144`, `song.py:225`) route through this function.
- **0004b** (`song.py:82-92`): the step-graph gate raises
  `_StepGraphUnavailable`, which is caught in `generate_song_tokens`
  (`song.py:45-46`) → falls back to the looped path. The new check sits inside
  a `try` whose `except ImportError: pass` cannot swallow
  `_StepGraphUnavailable` (not an ImportError) — correct.
- **0005** (`fa3.py:57-67`): try/except around the shared wrapper call, falling
  through to `torch.ops.aten._flash_attention_forward`. Arguments of the ATen
  call are unchanged; on CUDA the except branch is dead unless the wrapper
  raises (see P3-2).

### 1.4 DeepSelect CUDA-only claim — CONFIRMED

`upstream/sglang/python/sglang/kernels/ops/deep_select.py`:
- line 25: `_SUPPORTED_CAPABILITIES = ((9, 0), (10, 0), (10, 3))`
- lines 169-190: `is_deepselect_supported()` returns `False` when
  `torch.version.cuda is None` (and on capability mismatch); `topk()` raises
  `RuntimeError("DeepSelect does not support SM…")` (line 249) otherwise; the
  JIT build is nvcc/cutlass (`cuda_files=["deep_select/entry.cuh"]`,
  ptxas flags, `extra_dependencies=["cutlass"]`).

Live probe in the venv:
`python -c "import torch; from sglang.kernels.ops.deep_select import is_deepselect_supported; print(torch.version.cuda, is_deepselect_supported())"`
→ **`None False`** (device capability (11,5), gcnArchName `gfx1151`).

### 1.5 Platform-primitive probes (RCA §2 table) — REPRODUCED

Independent probe on gfx1151:
- shared `flash_attn_varlen_func`: **imports OK, fails at call time**
  (`ModuleNotFoundError: No module named 'flash_attn'`) — exactly the
  import/call split that patch 0005 addresses.
- `fa3.varlen_attention` via the patched fallback: OK, finite, shape (2,8,64).
- `"seqused_k" in str(torch.ops.aten._flash_attention_forward.default._schema)`
  → **True**.
- `SDPBackend.CUDNN_ATTENTION` / `FLASH_ATTENTION` / `EFFICIENT_ATTENTION` →
  `RuntimeError: No available kernel` (matches RCA; SDPA therefore falls to
  MATH, which `test_masked_sdpa_math_fallback` validates numerically).
- GraphAR `attention_backend="auto"` → resolves to **flash**
  (`cuda_graph.py:116-122` logic + `backend=flash` in the test diagnostic).

### 1.6 Test-quality audit — SOUND

- `test_aten_flash_varlen_numerics` (tests/test_yue2_rocm_fallbacks.py:71-93):
  `cu_k=[0,16,32]`, `seqused=[5,16]`, reference attends `k[0:5]` for row 0 and
  `k[16:32]` for row 1 — i.e., row 0 uses 5 kv, row 1 uses 16, per-row
  `seqused_k` semantics. GQA 8:2 expanded via `repeat_interleave(4)`; reference
  computed in fp32. My own re-measurement: max|diff| = **4.26e-3** (kv=5 row) /
  **3.79e-3** (kv=16 row), matching the "≈4e-3" claim. Control check
  (comparing row 1 against the wrong 5-kv slice) gives max|diff| ≈ 1.35 — the
  test genuinely discriminates correct seqused_k handling.
- `test_masked_sdpa_math_fallback` (lines 96-113): bool mask with
  `visible[..., 7:] = False`, comment "True = allowed" — correct PyTorch
  bool-mask semantics; reference restricts to the first 7 kv positions, GQA
  expanded, fp32. Passes at 0.04 s.
- `test_ar_graph_vs_eager_logits` (lines 152-190): constructs a **fresh
  `StaticKVCache`** and runs the model eagerly (`model(..., past_key_values=cache,
  use_cache=True, logits_to_keep=1)`) for both prefill and decode-step,
  independent of the GraphAR session's cache. Cross-kernel comparison
  (GraphAR/ATen-flash vs eager SDPA-MATH). Tolerance 0.05 × max(scale,1);
  measured < 5e-5.
- `test_reference_sampler_distribution_matches_fastpath_semantics`: assertions
  match the actual `distribution()` implementation (`sampling.py:31-62`) —
  semantic phase allows only MUSIC_END ∪ codec range, abc phase allows
  `[:EOD] ∪ {ABC_END}`, min_tokens blocks the end token, top-k caps at 50 —
  and agree with the fastpath masks (`fastpath.py:94-111`).

### 1.7 Model fixtures — CORRECT

`tests/test_yue2_rocm_fallbacks.py:28-29`:
`MODEL_DIR = /home/amd/Desktop/YuE2/models/YuE2-3B`,
`VAE_DIR = /home/amd/Desktop/YuE2/models/YuE2-Vae-legacy`. Both exist on disk.
The benchmark uses the same legacy decoder:
`benchmark/WildSongBench/code/generate.py:12` → `VAE = "m-a-p/YuE2-Vae-legacy"`;
`evidence/model_manifest.json` lists the role as "VAE decoder (benchmark legacy)"
(m-a-p/YuE2-Vae-legacy @ b54118f). No non-legacy VAE is referenced or downloaded.

### 1.8 compatibility_tests.json vs own run — MATCHES (outcomes), durations inaccurate

All 10 test names and outcomes (`passed`, total 10 / passed 10 / failed null)
match my re-run exactly. However every `duration_s` is recorded as `0`,
whereas real per-test durations are 18.14 s / 2.84 s / 0.60 s / 0.33 s / 0.28 s /
0.27 s / 0.04 s / 0.04 s (see §1.1). See P3-1.

## 2. Issues

**P0** — none.

**P1** — none.

**P2-1 — patches/README.md misstates the batched-AR gate on gfx1151.**
`patches/README.md` ("Not patched" section, last bullet) claims: *"batched.py
batched-AR (SGLANG_YUE2_BATCHED_AR): requires the DeepSelect
BatchedGraphSampler; with patch 0004 the gate keeps it off on gfx1151."*
This is factually wrong. Patch 0004 touches only `fastpath.py` and `song.py`;
the batched entry gate `batched_ar_enabled()`
(`upstream/sglang/python/sglang/srt/models/yue2/batched.py:38-39`) is
env-var-only and **defaults to ON**, and `BatchedGraphSampler` is constructed
without any support check (`batched.py:101`, `batched.py:223`). On a
default-env gfx1151 server with ≥2 grouped requests the actual sequence is:
batched ABC prefill runs, then `sample_in_graph` → `topk()` raises
`RuntimeError("DeepSelect does not support SM115")` (caught at
`batched.py:329`), then the fallback `_abc_per_request` **hardcodes
`use_fast_sampler=True`** (`batched.py:279`), bypassing the patched
`fast_sampler_available()` gate, so `FastSampler.topk()` raises again
mid-ABC-decode, and only the stage-level broad except
(`multimodal_gen/.../yue2/ar.py:156-157`) lands the requests on the correct
per-request reference path. Net effect: requests still complete correctly, but
every grouped batch pays two exception round-trips and wasted prefills, with
stack traces in the logs. The delivered ROCm run is unaffected because the
launcher sets `SGLANG_YUE2_BATCHED_AR=0` (report §4), and no patch in this
series introduces the problem — but the README claim must not stand as written.
**Exact fix required** (either is acceptable):
(a) correct `patches/README.md` to state that batched-AR is env-gated only
(default on), is protected on gfx1151 solely by stage-level exception
fallback, and that `SGLANG_YUE2_BATCHED_AR=0` is required for clean ROCm
operation; or
(b) extend the patch series: add an `is_deepselect_supported()` check to
`batched_ar_enabled()` (or to `run_batched_ar` entry) and change
`batched.py:279` to `use_fast_sampler=None` so `_abc_per_request` respects the
patched gate. Re-run the suite after either fix.

**P3-1 — compatibility_tests.json durations are zero-filled.** All
`duration_s` fields are `0`; real durations are nonzero for at least 8 of 10
tests (e.g., `test_vae_decode_finite` 18.14 s). Fix: regenerate the JSON with
actual per-test durations (e.g., pytest `--json-report` or
`--durations=0` parsing).

**P3-2 — fa3.py `except Exception` is broader than necessary**
(`fa3.py:60`). On CUDA a genuine wrapper failure (bad args, OOM, kernel bug)
would be silently rerouted to the ATen op, masking the error. Fix (optional):
narrow to `(ImportError, ModuleNotFoundError, RuntimeError,
NotImplementedError)` and emit a one-line warning when the fallback triggers.

**P3-3 — stale docstring in test_aten_flash_varlen_numerics.** The docstring
says "(SGLANG_YUE2_FA3=0 path)", but with the env unset the test runs under
the default flag (=1) and actually exercises patch 0005's call-time fallback
(shared wrapper imports, call fails, falls through to ATen) — which is the
stronger claim. Fix: reword, and optionally add an explicit
`SGLANG_YUE2_FA3=0` sub-case via `monkeypatch.setenv`.

**P3-4 (informational) — aiter-less HIP + hypothetical Quark-int4fp8 model.**
With `shuffle_weight = None`, `quark_int4fp8_moe.process_weights_after_loading`
(`quark_int4fp8_moe.py:355-376`) would run the CDNA3 scale tweak and then fail
loudly with `TypeError` on `shuffle_weight(None(...))` at weight-processing
time. Loud crash before serving, no silent corruption; YuE2 (bf16) unaffected.
Consistent with the README's stated tradeoff; no action required for this
phase. (`quark_w4a4_mxfp4_moe.py` likewise retains unguarded aiter imports
behind the explicit `SGLANG_USE_AITER` opt-in, `quark_w4a4_mxfp4_moe.py:51-59`
— out of scope.)

## 3. Conclusion

The patch series is minimal, byte-reproduced in the live tree, and confined to
the six claimed files; sampling math, tokenization, seeds, ODE and weight
loading are untouched; the DeepSelect CUDA-only root cause and all §2 platform
claims were independently reproduced on gfx1151; the 10-test suite passes from
a clean default environment; the tests validate the exact semantics they claim
(seqused_k per-row caps, bool-mask True=allowed, GQA 8:2, GraphAR-vs-eager on
real weights); fixtures match the benchmark decoder. Phase gate ("AR, NAR and
VAE each execute on gfx1151 with finite outputs") is met. The one P2 is a
documentation-accuracy error in patches/README.md about the batched-AR gate
(operational noise, not a correctness failure, and not reached under the
documented launcher flags).

**Verdict: PASS**
