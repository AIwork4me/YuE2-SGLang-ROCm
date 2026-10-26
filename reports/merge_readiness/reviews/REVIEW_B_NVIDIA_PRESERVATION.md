# Review B — NVIDIA/CUDA Preservation (YuE2 SGLang integration preview)

- **Reviewer role:** independent CUDA-preservation review (Review B of three)
- **Repo:** `/home/amd/Desktop/YuE2/upstream/sglang-merge`, branch `integration/yue2-sglang-gfx1151-merge-ready`, HEAD `bcb496ab9`
- **Comparison refs:** author PR #42106 head `ced0ef7d1` (`authorfork/add_yue2`), ROCm reference `def437fb7` (`myfork/fix/yue2-rocm-reference`), lint `1a9f2d92a` (cherry-picked into HEAD lineage as `6b368483f`), upstream main `5ef99013a`
- **Method:** direct code reads plus `git show/diff` and per-function `ast.dump` comparisons between revisions; no network, no GPU execution (host is AMD gfx1151).
- **Verdict protocol:** P0/P1/P2/P3; end verdict at bottom.

---

## 0. Scope sanity

`def437fb7` (the ROCm-guards commit) touches exactly 5 files — `fastpath.py`, `song.py`, `fa3.py`, `batched.py`, plus the new `test_yue2_platform_gates.py` (verified via `git show def437fb7 --stat`). Every other yue2 file's ced0ef7d→HEAD delta comes from the lint cherry-pick (`6b368483f`, 29 files, all yue2-scoped + `.codespellrc` + `kernels/ops/deep_select.py`), the merge of main (`6a8757026`, which among yue2 files only re-resolved `http_server.py`), the ruff-format fixup (`5dc9b33a8`, 2 files × cosmetic), and the route-loader fix (`bcb496ab9`). **No core sglang CUDA file outside the yue2 tree was touched by the author PR, the lint commit, or the guards commit** (lint stat confirmed; merge-of-main only re-resolved `http_server.py` in the yue2-relevant set).

AST evidence (docstring-stripped `ast.dump`, per-function for the guards files): all of `models/yue2/{nar,nar_fast,modeling_yue2,modeling_vae,storage,generation,tokenization_yue2,cuda_graph}.py`, `models/yue2/__init__.py`, `yue2_loader.py`, `yue2_parallel.py`, and the multimodal `yue2/{ar,artifacts,vae}.py` stages are **AST-identical author ced0ef7d → HEAD**. The four files whose AST legitimately differs do so only in the lint commit's declared benign classes: `sampling.py` (function-level import moved after the docstring), `protocol.py` (isort alias order in a module-level import), `request.py` / `yue2_loader.py` (quote-annotation unquoting `"Yue2Request"` → `Yue2Request` under `from __future__ import annotations`), `streaming.py` (import consolidation), `configs/pipeline_configs/yue2.py` (codespell comment + reflow). None of these are executable-path changes.

## 1. The six CUDA fast paths, function by function

### 1.1 Step Graph — `python/sglang/srt/models/yue2/song.py`

- Entry gate `generate_song_tokens` (song.py:51-56): `cfg_scale == 1.0 and request.cot != "off" and SGLANG_YUE2_STEP_GRAPH=="1" and session.device.type == "cuda"` — **character-for-character the author's gate** (ced0ef7d song.py lines 30-33), including the `try/except _StepGraphUnavailable → looped` wrapper.
- `_generate_song_tokens_step_graph` (song.py:101): author prologue `if _load_topk_backend() is None: raise _StepGraphUnavailable(...)` retained verbatim (song.py:119-120). def437fb **added** one check after it (song.py:121-126): `if not deepselect_runnable(): raise _StepGraphUnavailable("DeepSelect kernel unsupported on this device")`. The raise happens **before** `GraphSampler` construction and before `session.step_mode = True`, so no session-state pollution on the fallback path.
- Everything after the prologue — `sample_phase` closure, forced-transition loop, timing dicts — is AST-identical to the author's (per-function AST comparison def437fb vs HEAD: all identical; module diff is docstring whitespace + isort merging the two `.fastpath` import blocks).
- On a supported CUDA SM (9.0/10.0/10.3): `deepselect_runnable()` → `is_deepselect_supported()` → True → check is a no-op → identical execution. On unsupported: author crashed (a `RuntimeError` from `topk()`'s SM check inside `sample_phase`/capture is *not* `_StepGraphUnavailable`, so it propagated); integration head falls back to `_generate_song_tokens_looped`. Delta exists only where the author crashed. **Preserved.**

### 1.2 Fast Sampler — `python/sglang/srt/models/yue2/fastpath.py`

- `_load_topk_backend()` (fastpath.py:31-48): identical to author (in-tree `sglang.kernels.ops.deep_select` preferred, pip `deep_select` fallback).
- Author's `fast_sampler_available()` was `env != "1" → False; backend missing → False; try: torch.cuda.is_available()`. def437fb split it into `deepselect_runnable()` (fastpath.py:51-70) + delegation (fastpath.py:73-76). The pip-backend branch keeps the author's **exact** predicate: `if probe is None: return torch.cuda.is_available()` (fastpath.py:66-67). The in-tree branch adds `bool(probe())` where `probe = is_deepselect_supported` (already present in the author's vendored module at ced0ef7d — `git diff ced0ef7d def437fb -- .../ops/deep_select.py` is empty).
- `FastSampler.sample_token`, `GraphSampler.*`, `BatchedGraphSampler.*` (the actual CUDA math: masking, `_window_penalty_`, `backend.topk(sorted=True, indices_type=int64, return_value=True)`, softmax/cumsum top-p, `torch.multinomial(generator=...)`): per-function AST def437fb vs HEAD **all identical**; def437fb vs ced0ef7d introduced **zero** changes inside these classes (the ced0ef7d→def437fb diff touches only the two availability functions).
- On supported CUDA the predicate outcome is identical; on unsupported SMs/ROCm the author engaged and then raised `RuntimeError("DeepSelect does not support SMxx")` at first `topk()` (vendored deep_select.py:246-249, unchanged since ced0ef7d); head returns False → reference sampler. **Preserved.**

### 1.3 FA3 varlen — `python/sglang/srt/models/yue2/fa3.py`

- def437fb's only code change: `if os.environ.get("SGLANG_YUE2_FA3","1")=="1"` → `... == "1" and torch.version.hip is None` (fa3.py:32). The `try: from sglang.kernels.ops.attention.flash_attention import flash_attn_varlen_func / except Exception: _VARLEN = False` structure is the author's, untouched (fa3.py:33-40).
- **CUDA host, wrapper imports** (normal H800 case): `torch.version.hip` is None → condition True → same import → `_VARLEN` set → `varlen_attention` (fa3.py:58-71) calls the shared op with the author's exact kwargs (`seqused_k=`, `causal=False`, `ver=3`). Verified the shared op's signature at HEAD (`kernels/ops/attention/flash_attention.py:228`) still accepts these (and existed at ced0ef7d line 224). **Identical to ced0ef7d.**
- **CUDA host, wrapper unavailable**: the new `hip is None` conjunct is True, the import raises, the author's `except Exception` still catches it → `_VARLEN = False` → `fa3_available()` False → `torch.ops.aten._flash_attention_forward` fallback (fa3.py:72-84). **Identical to ced0ef7d.** The added conjunct can only be False on a ROCm torch build, where the author's behavior was an import success followed by a CUDA-only kernel failure at call time.
- The `torch.version.hip` read is cheap, cached after first `_load_varlen()` (`_LOADED` flag, author's mechanism). **Preserved.**

### 1.4 Batched AR — `python/sglang/srt/models/yue2/batched.py`

- `batched_ar_enabled()` (batched.py:40-46): author = `env == "1"`; head = `env != "1" → False` else `deepselect_runnable()`. Env semantics byte-identical; capability conjunct added. It deliberately does **not** consult `SGLANG_YUE2_FAST_SAMPLER` — matching the author's independence of the two knobs (test 20 pins this).
- The consumer in the AR stage (`multimodal_gen/.../yue2/ar.py:155-160`) is AST-identical to the author's; `run_batched_ar`, `generate_semantic_batched`, `generate_abc_batched` and their per-request fallbacks are AST-identical to the author's. `default_batched_pool` / `GraphSessionPool` construction is left ungated (PyTorch CUDA-graph pooling, as the def437fb message promises) — pooling itself contains no DeepSelect dependency; only `BatchedGraphSampler` does, and it is now unreachable on unsupported devices.
- On supported CUDA: `deepselect_runnable()` True → batched path identical. On unsupported: author constructed `BatchedGraphSampler` and failed at capture/first `topk`; head routes per-request. **Preserved.**

### 1.5 Fused decode — `python/sglang/srt/models/yue2/cuda_graph.py`

- def437fb did **not** touch this file (`git diff ced0ef7d def437fb -- cuda_graph.py` empty). Its 417-line ced0ef7d→HEAD delta is entirely the lint reformat: **AST-identical (docstrings stripped) author → HEAD**, verified programmatically. The author's own gates survive verbatim: `SGLANG_YUE2_FUSED_DECODE` (`_fused_enabled()`, cuda_graph.py:30-31, 264), `device.type == "cuda"` capture guard (cuda_graph.py:153), fused-attention eligibility (cuda_graph.py:163-164).
- The capability gating that protects this path on unsupported devices lives one level up (song.py step-graph prologue / batched_ar_enabled), before any capture is attempted. **Preserved (byte-equal modulo ruff).**

### 1.6 Fast NAR — `python/sglang/srt/models/yue2/nar.py` (+ `nar_fast.py`, multimodal `yue2/nar.py`)

- Neither def437fb nor the merge changed any logic here: `srt/models/yue2/nar.py`, `nar_fast.py` and the multimodal NAR stage are AST-identical author → HEAD. The author's own capability gates are intact: `SGLANG_YUE2_FAST_NAR` (multimodal nar.py:43, 124), `_sgl_kernel()` import probe with `FLASHINFER_DISABLE_VERSION_CHECK` note (nar_fast.py:23-38), `synthesize_from_session` `except ValueError → reference NAR` (multimodal nar.py:128-155), batched-NAR `_NarBatchUnsupported` routing (nar.py:40-46). The ROCm guards commit needed to add nothing here because the author already fail-soft'd this path. **Preserved (identical).**

## 2. DeepSelect duplication

Facts established:

1. **Two modules coexist at HEAD**: author's `python/sglang/kernels/ops/deep_select.py` (10,835 B; `_INPUT_STRIDE_ALIGNMENT_BYTES = 1024`, probe named `is_deepselect_supported`, API with `begin/end/hint/output_idx/abort_when_nan_found`) and main's `python/sglang/kernels/ops/attention/deep_select.py` (12,856 B; `_INPUT_STRIDE_ALIGNMENT_BYTES = 128`, probe named `is_deep_select_supported`, plus `topk_page_transform`, `get_output_stride_alignment_bytes`, `_precompile`, `_CachedModuleDispatch` cluster tiers).
2. **No cross-imports**: the author's module imports only `sglang.kernels.jit.utils`; main's imports `jit.utils` (+ lazy `jit.utils.occupancy` inside `_cluster_tiers`). Neither imports the other (grep-verified).
3. **No `__init__` auto-import**: `kernels/ops/__init__.py` eagerly imports only the 20 RFC groups (`_GROUPS`); `deep_select` is not a group, and the file is byte-identical author → HEAD. `ops/attention/__init__.py:335-341` registers `attention.deep_select_topk` against main's module via a `KernelSpec` **target string** — `register_kernel` is metadata-only (`kernels/registry.py:76-78`), the target is imported lazily by `get_kernel`, which yue2 never calls.
4. **Resolution**: `fastpath._load_topk_backend`'s `from sglang.kernels.ops import deep_select` (fastpath.py:36) is the **only** reference to the top-level module in the tree (grep-verified) and binds the author's module. The probe names differ (`is_deepselect_supported` vs `is_deep_select_supported`), so `deepselect_runnable`'s `getattr` can never accidentally satisfy itself against main's function.
5. **Shared JIT/csrc coexistence**: both wrappers `load_jit("deep_select_topk", ...)` from the same `csrc/deep_select/vendor` tree. The vendored `TopkSelectConfig` template (`csrc/deep_select/vendor/cuda_kernels/config.h:5-13`) takes the author's 13 parameters with `page_transform_ = false` **defaulted** as the 14th, so the author's instantiation still compiles; `load_jit`'s cache key covers the full arg tuple plus wrappers/flags (`jit/utils/compile/loader.py:114-133`), and the two wrappers pass different-arity arg tuples, so their build-cache scopes do not collide. History check: the csrc last changed in `8151378c1` which is an ancestor of **both** ced0ef7d and main — the merge did not alter the vendored C++ under either wrapper.

**Judgement on the duplication:** keeping the author's module is the correct NVIDIA-preserving choice, and swapping yue2 onto main's module would have been the risky move, for concrete reasons: (a) main's public input-alignment contract is 128 B while the vendored CUDA kernel's TMA path hard-requires 1024 B (`common_parts.cuh:516,533` — `INPUT_STRIDE_ALIGNMENT_REQUIREMENT = 1024` in `structs.h:6`); yue2's scores rows are padded to `STRIDE_FLOATS = 256` floats = 1024 B (fastpath.py:79,96-97,199). Feeding main's wrapper/API into yue2's buffers would either violate the layout contract or force re-padding every graph-resident buffer — a silent-behavior-change vector, not a refactor. (b) main's `topk` has a different signature/return handling and cluster-tier dispatch tuned for DSV4 indexer shapes; yue2's `GraphSampler`/`BatchedGraphSampler` call sites (`self.backend.topk(..., sorted=True, indices_type=torch.int64, return_value=True)`) are validated against the author's API. (c) The alternative — deleting the author's module and rewriting yue2 against `ops.attention.deep_select` — would be a functional change to a PR the mission says must stay logically untouched. Flagged as **P2 maintainability** (see findings): two same-purpose kernels wrappers with near-identical JIT names and one shared csrc will confuse future maintainers and invites an accidental "dedup" that would change NVIDIA behavior; it needs an explicit upstream convergence plan, but for *this* merge, retention is the safe direction.

## 3. Env-var truth tables (supported CUDA device, e.g. H800 SM 9.0)

Predicates: `RUN` = `deepselect_runnable()`; at ced0ef7d the corresponding predicate was `backend ∧ torch.cuda.is_available()` (`AVAIL`). On a supported device with the in-tree backend both are True; with the pip backend head keeps `AVAIL` verbatim.

### SGLANG_YUE2_FAST_SAMPLER (`fastpath.fast_sampler_available`)
| env | BEFORE (ced0ef7d) | AFTER (HEAD) | same? |
|---|---|---|---|
| unset / "1" | `AVAIL` → True → FastSampler | `RUN` → True → FastSampler | YES |
| "0" | False → reference | False → reference | YES |

### SGLANG_YUE2_STEP_GRAPH (`song.generate_song_tokens`)
| env (cfg=1, cot≠off, cuda session) | BEFORE | AFTER | same? |
|---|---|---|---|
| unset / "1", backend ok | step graph | `RUN` True → step graph | YES |
| unset / "1", backend missing | `_StepGraphUnavailable` → looped | same (probe short-circuits on missing backend) | YES |
| "0" | looped | looped | YES |

### SGLANG_YUE2_FA3 (`fa3._load_varlen`)
| env | host | BEFORE | AFTER | same? |
|---|---|---|---|---|
| unset/"1" | CUDA, wrapper imports | shared FA3 op (`ver=3`) | shared FA3 op | YES |
| unset/"1" | CUDA, wrapper broken/missing | aten `_flash_attention_forward` | aten (try/except retained) | YES |
| "0" | CUDA | aten | aten | YES |
| unset/"1" | ROCm | import ok → kernel failure at call time (crash) | aten varlen directly | **delta = crash → fallback (intended)** |

### SGLANG_YUE2_BATCHED_AR (`batched.batched_ar_enabled`)
| env | BEFORE | AFTER | same? |
|---|---|---|---|
| unset / "1" | True → BatchedGraphSampler | `RUN` True → BatchedGraphSampler | YES |
| "0" | False → per-request | False → per-request | YES |

Unsupported-device deltas (author crash → head fallback): CUDA SM ∉ {9.0, 10.0, 10.3} and any ROCm host, for FAST_SAMPLER (crash at first `topk()`), STEP_GRAPH (`RuntimeError` escaping the `_StepGraphUnavailable` net), BATCHED_AR (crash at capture/first `topk`). No supported-device delta found in any of the four knobs. (For completeness: `SGLANG_YUE2_FUSED_DECODE`, `SGLANG_YUE2_FAST_NAR`, `SGLANG_YUE2_VELOCITY_GRAPH`, `SGLANG_YUE2_GRAPH_POOL`, `SGLANG_YUE2_BATCHED_POOL` are all author-original and untouched.)

## 4. The 21-test suite — `test/registered/unit/models/test_yue2_platform_gates.py`

Read in full; 21 test functions counted. Honest assessment:

- **What the CUDA-positive cases prove:** with a fake supported backend (`FakeBackend(supported=True)`), `fast_sampler_available()`/`deepselect_runnable()` return True (tests 1, 20); with simulated CUDA (`torch.version.hip=None`) and an injected shared op, `varlen_attention` dispatches to the shared op with the author's exact kwargs `seqused_k`/`causal=False`/`ver=3` (test 14); the step-graph prologue is passable on a supported device, proven by `GraphSampler` construction count + tripping the *next* upstream guard (`"already captured"`), both in the inner function and through the public `generate_song_tokens` entry (tests 9, 11); env knobs still win (tests 6, 12, 16, 19); the pip backend without a probe keeps `torch.cuda.is_available()` (test 5); FAST_SAMPLER=0 does not disable batched AR (test 20); missing shared-op module → aten fallback (test 15). These are genuine dispatch-level regression nets: if anyone later "simplifies" a gate to be device-blind or env-blind, these fail.
- **What they do NOT prove:** they are simulated dispatch tests, exactly as the module docstring admits ("dispatch proofs, not GPU execution proofs"). `FakeBackend.topk` asserts it is never called; `StubGraphSampler` never captures a graph; the FA shared op is a lambda. Nothing here executes DeepSelect on SM 9.0/10.0/10.3, captures/replays a real CUDA graph, or checks numerics of `sample_in_graph`. Two of the 21 are `skipif(not torch.cuda.is_available())` — note that on a ROCm host `torch.cuda.is_available()` is also True, so "supported device" entry tests would run there with a fake backend. **Physical H800 validation of the author's fast paths remains with the PR author and is not discharged by this suite.** That is correctly scoped, not a defect of the merge.

## 5. Lint cherry-pick (1a9f2d92 → 6b368483f) and conflict-resolution spot checks

- 29 files, all yue2-scoped plus `.codespellrc` and `kernels/ops/deep_select.py`; no core sglang CUDA infrastructure file touched (stat-verified).
- `kernels/ops/deep_select.py`: diff is one import reorder (`make_cpp_args` moved above the consolidated `jit.utils` import) + one trailing-whitespace line — zero executable-AST change; the file is otherwise byte-identical to ced0ef7d.
- `http_server.py` (lint hunk): one blank line added inside the route-loader block. No CUDA relevance.
- `http_api.py` (lint): isort import reorder + ruff reflow only (comment/blank-stripped diff vs author shows import lines and line-wrapping exclusively).
- `bcb496ab9` (route-loader path fix, post-merge): `_Path(...)/"experimental"/"yue2"/"http_api.py"` → `.../"yue2"/"http_api.py"` following main's flattening. Verified `yue2/http_api.py` exists at HEAD and `experimental/yue2` does not. HTTP-layer only; zero CUDA impact.
- The merge-of-main (`6a8757026`) resolved conflicts only in `http_server.py` within the yue2-relevant set; `5dc9b33a8` re-canonicalized 2+1 lines in `fa3.py`/`song.py`. Combined with the per-function AST results in §1 and §0, no logic edits slipped in through the lint or merge path on any CUDA-relevant file.

## 6. Uncommitted working-tree overlay (4 files)

`git diff` shows exactly one hunk per file, each **strictly inside** a `_is_hip`/`elif _is_hip:` block:
- `layers/moe/moe_runner/triton_utils/fused_moe.py`: the `elif _is_hip:` `sgl_kernel` activation import wrapped in try/except → None. The preceding `if _is_cuda:` branch is untouched (hunk context confirms it sits above the change).
- `layers/quantization/quark/schemes/quark_w4a4_mxfp4.py`, `.../quark_w4a4_mxfp4_moe.py`, `layers/quantization/quark_int4fp8_moe.py`: `if _is_hip:` aiter import guards.

On an NVIDIA host `_is_hip` is False, so none of these statements execute; there is no change to any statement reachable on CUDA. The overlay does not touch yue2, kernels, or dispatch logic. **Confirmed: NVIDIA paths unaffected.** (Note for the record: the overlay is uncommitted and self-labelled as an independent-main-PR candidate; it should not ride along in the YuE2 PR.)

---

## Findings

- **P0 — none.**
- **P1 — none.**
- **P2-1 (maintainability, dup kernel wrapper):** two live DeepSelect wrappers (`kernels/ops/deep_select.py` vs `kernels/ops/attention/deep_select.py`) with different alignment contracts (1024 B vs 128 B), different probe names and different `topk` APIs, both JIT-compiling from the same `csrc/deep_select/vendor` tree under the same `load_jit("deep_select_topk", ...)` kernel name. Correct choice today (§2), but a future "dedup" that repoints `fastpath._load_topk_backend` at `ops.attention.deep_select` would silently change NVIDIA behavior (layout contract, API, cluster dispatch). Request: an inline comment at `fastpath.py:36` stating the module choice is deliberate (1024 B row contract, author API) and an upstream convergence issue. Not a merge blocker.
- **P2-2 (test evidence boundary):** the 21-case suite proves dispatch, not execution. Physical H800 (SM 9.0) validation of Step Graph / Fast Sampler / FA3 varlen / Batched AR numerics is still outstanding and owned by the PR author; the suite cannot substitute for it (and says so honestly). Should be tracked as an explicit pre-merge condition on the NVIDIA side.
- **P3-1 (multi-GPU probe edge):** `is_deepselect_supported()` probes `torch.cuda.current_device()` when no device is passed (`kernels/ops/deep_select.py:169-190`), while the author's `torch.cuda.is_available()` was device-agnostic. On a heterogeneous CUDA host whose current device is unsupported while the model runs on a supported one, head falls back where the author engaged (the kernel itself checks `input.device`, so the author's engagement would have worked there). Obscure configuration; note only.
- **P3-2 (minor gate redundancy):** in `song._generate_song_tokens_step_graph` the `_load_topk_backend() is None` check (song.py:119-120) is now subsumed by `deepselect_runnable()`'s backend check; kept for the author's error-message fidelity. Harmless.
- **P3-3 (overlay hygiene):** the 4-file HIP-only overlay is uncommitted; it is inert on CUDA (verified) but should be committed separately or dropped before the PR is submitted so review surface stays clean.

## What was verified positively

1. All six fast paths: gating adds checks only for absent capability; author-authored fast-path bodies are untouched (per-function AST evidence, §1).
2. DeepSelect duplication is interference-free at HEAD (no cross-imports, no auto-import, lazy registry, unique probe names) and retention of the author's module is the NVIDIA-safe choice (§2).
3. FA3 CUDA behavior identical to ced0ef7d on CUDA hosts both when the wrapper imports and when it does not (§1.3).
4. Env-var truth tables identical on supported devices for all four knobs; deltas confined to previously-crashing unsupported platforms (§3).
5. Lint/merge/ruff/fix commits carry no logic edits into CUDA-relevant files (§0, §5); working-tree overlay is HIP-only (§6).

---

## Overall verdict

**PASS-WITH-P2s** — no P0/P1. The NVIDIA CUDA fast paths are logically preserved at HEAD `bcb496ab9`; the two P2s are a maintainability guard-rail request (document the DeepSelect module choice) and the standing requirement of physical H800 validation, which this merge correctly does not claim to discharge.
