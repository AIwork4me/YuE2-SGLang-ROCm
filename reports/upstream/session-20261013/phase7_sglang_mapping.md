# Phase 7 — Omni ROCm Gates → SGLang PR #42106 Source Mapping

 Analyst: independent source-compatibility review
 Target: sgl-project/sglang PR #42106 (`add_yue2`), head `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`
 Method: `gh api` file fetches at the PR ref; cross-verified against local mirror
 `/workspace/yue2-omni-pr/sglang-src` whose `python/sglang/srt/models/yue2/{song,fastpath,fa3,batched}.py`
 are byte-identical to the fetched PR blobs. Omni gates from
 `/workspace/yue2-omni-pr/repo/sglang_omni/models/yue2/` @ HEAD 50c91c0.

## PR #42106 changed-file surface (yue2-relevant)

- `python/sglang/srt/models/yue2/` — 16 files (`batched, cuda_graph, fa3, fastpath, generation,
  modeling_vae, modeling_yue2, nar, nar_fast, protocol, sampling, song, storage, streaming,
  tokenization_yue2, __init__`). **No `stages.py`** — no omni-style factory/scheduler lives here.
- `python/sglang/srt/distributed/yue2_parallel.py`, `python/sglang/srt/model_loader/yue2_loader.py`
- `python/sglang/multimodal_gen/...` (pipeline, stages `ar.py`/`nar.py`/`vae.py`, configs, http)
- `python/sglang/kernels/ops/deep_select.py` — **ships `is_deepselect_supported()` (line 169)**:
  returns False when `torch.version.cuda is None` (ROCm) or capability ∉ {(9,0),(10,0),(10,3)}.
- Platform utility available to PR code: `sglang.srt.utils.common.is_hip()` (mirror line 138).
  PR yue2 files import **no** platform helper today.

## Mapping table

| # | Omni gate (file:line) | PR #42106 equivalent (path:line) | Existing platform gate? | Verdict | Minimal hunk shape |
|---|---|---|---|---|---|
| 1 | `stages.py:46` factory admission `is_cuda() or is_rocm()`; `stages.py:59` ROCm batch default 4→1; `stages.py:50-51` cudnn disable | No stages.py. Closest: `multimodal_gen/runtime/pipelines/yue2_pipeline.py:44` (`torch.device("cuda", ...)` hardcoded), stages `model_specific_stages/yue2/ar.py` (no platform import at all), loader `yue2_loader.py` (no platform check) | **None** — no is_cuda/is_rocm/is_hip/current_platform anywhere in the pipeline/stages/loader. cudnn-disable has no equivalent (only `cuda_graph.py:122-125` attention-backend selection, auto→"flash"). Batch default "4" is omni-scheduler-specific; PR batching = scheduler dynamic batching + `ar.py:148` `batched_ar_enabled()` | **NEEDS_GATE** (admission via capability, not platform); batch-default & cudnn hunks **NOT_APPLICABLE** (omni-specific) | Functional equivalent = gate `batched_ar_enabled()` (`batched.py:38-39`) on `fast_sampler_available()` so ROCm runs per-request AR (patch 0004 extension). Optional: `is_hip()` admission assert in `Yue2Pipeline.load_modules` |
| 2 | `song.py:42-45` bypass fused decode+sample step graph on ROCm (`not current_platform.is_rocm()`) | `srt/models/yue2/song.py:37-39`: condition = `cfg_scale==1.0 and cot!="off" and SGLANG_YUE2_STEP_GRAPH=="1" and session.device.type=="cuda"` | **None** — `device.type=="cuda"` is True on HIP; `song.py:80-81` only checks `_load_topk_backend() is None`, but the in-tree wrapper (`fastpath.py:35`) imports fine on ROCm → guard passes → `topk()` raises mid-graph-capture | **NEEDS_GATE** | In `_generate_song_tokens_step_graph` after line 81: `from sglang.kernels.ops.deep_select import is_deepselect_supported; if not is_deepselect_supported(): raise _StepGraphUnavailable(...)` (= patch 0004 song hunk). Omni-shape alt: append `and not is_hip()` to the line 37-39 condition |
| 3 | `fastpath.py:75-79` `fast_sampler_available()` → False on ROCm | `srt/models/yue2/fastpath.py:50-58`: env flag ∧ backend import ∧ `torch.cuda.is_available()` | **None** — keys on `torch.cuda.is_available()` (True on HIP); conflates importability with runnability; `song.py:215` then builds FastSampler on HIP | **NEEDS_GATE** | Replace `return torch.cuda.is_available()` (line 57) with `if not torch.cuda.is_available(): return False; from sglang.kernels.ops.deep_select import is_deepselect_supported; return is_deepselect_supported()` (= patch 0004 fastpath hunk). Omni-shape alt: early `if is_hip(): return False` |
| 4 | `fa3.py:32-33` skip shared FA3 varlen op on ROCm → native ATen | `srt/models/yue2/fa3.py:28` `_load_varlen()` gated only by `SGLANG_YUE2_FA3=="1"`; call at `fa3.py:55-57` | **None** — import of the shared wrapper succeeds on ROCm (pure-python); kernels are CUDA-only → fails at call time mid-forward | **NEEDS_GATE** | Either (a) omni-shape: `== "1" and not is_hip()` at `fa3.py:28`; or (b) patch 0005 shape: wrap the `varlen(...)` call (lines 55-57) in try/except falling through to `torch.ops.aten._flash_attention_forward` (line 58-60). (b) is strictly more general (also covers flash_attn-less CUDA hosts) |

## Comparison with evidence-repo patch series

| Patch | Files touched | In PR #42106 file list? | Relation |
|---|---|---|---|
| 0001 `quark_w4a4_mxfp4.py` aiter guard | `srt/layers/quantization/quark/schemes/...` | No (upstream main path) | Unrelated to yue2; import-chain fix so any model (incl. YuE2) loads without aiter on gfx1151 |
| 0002 `quark_w4a4_mxfp4_moe.py` | same dir | No | Same |
| 0003 `quark_int4fp8_moe.py` | `srt/layers/quantization/...` | No | Same |
| 0004 `batched.py`+`fastpath.py`+`song.py` DeepSelect gates | `srt/models/yue2/{batched,fastpath,song}.py` | **Yes — PR-added files** | **Direct overlap: these ARE gates 1(fn)/2/3** |
| 0005 `fa3.py` ATen fallback | `srt/models/yue2/fa3.py` | **Yes** | **Direct overlap: gate 4** |
| 0006-0007 wsb evaluator | `wsb_metrics/...` (outside sglang) | No | Evaluation harness, not upstream material |
| 0008 kvcacheio guards | `srt/mem_cache/{hisparse_memory_pool,memory_pool_host,pool_host/mha}.py` | No (upstream main paths) | Import-chain fix; YuE2-irrelevant but boot-blocking without sgl_kernel on ROCm |

Conflict risk vs #42106's state: GitHub reports `mergeStateStatus: UNKNOWN / mergeable: UNKNOWN`
(large PR; mergeability not computed). All 0004/0005 hunks land exclusively in PR-added files, so
no conflict with `main` — only with future author edits to the same four functions
(`batched_ar_enabled`, `fast_sampler_available`, `_generate_song_tokens_step_graph`,
`varlen_attention`). 0001-0003/0008 touch base-branch files untouched by the PR → zero
PR-conflict risk, but belong on `main` (or a ROCm-port branch), not inside the YuE2 feature PR.

## Integration-route recommendation

Propose **3 small guards as a follow-up commit to `add_yue2`** (after the author resolves the
current conflicts/DIRTY state), each ≤10 lines, all keyed on the PR's own
`is_deepselect_supported()` rather than platform sniffing:

1. `song.py` step-graph entry → `is_deepselect_supported()` else `_StepGraphUnavailable`
2. `fastpath.py::fast_sampler_available()` → consult `is_deepselect_supported()`
3. `fa3.py::varlen_attention()` → try/except fall-through to ATen (or `is_hip()` in `_load_varlen`)

Optionally a 4th (review-polish): `batched.py::batched_ar_enabled()` → consult
`fast_sampler_available()` (avoids noisy per-request BatchedUnsupported fallbacks on ROCm).
Route 0001-0003/0008 to upstream `main` as independent ROCm-portability PRs; do not bundle them
into #42106.

## Risk notes

- `is_deepselect_supported()` semantics: relies on `torch.version.cuda is None` for ROCm; if a
  future ROCm build sets `torch.version.cuda`, the capability check (gfx1151 → (11,5) ∉ supported)
  still returns False. Safe.
- Omni's `torch.backends.cudnn.enabled=False` has no PR equivalent, but the PR's
  `cuda_graph.py:122` auto-selection resolves to "flash" on ROCm and the `cudnn` branch is never
  auto-selected (validated in evidence README "Not patched" section) — acceptable gap, note only.
- Capability-keyed gating (chosen) also disables the paths on pre-Hopper CUDA GPUs — a behavior
  change for e.g. SM 8.x hosts that today would likewise crash at `topk()`; net improvement, but
  flag it to the author.
- If the author independently adds equivalent gates while resolving DIRTY state, rebase drop
  duplicates before proposing.

PHASE7_VERDICT: PASS
