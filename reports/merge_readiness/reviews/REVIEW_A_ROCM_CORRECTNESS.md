# Review A — ROCm correctness (YuE2 SGLang integration preview)

- Reviewer role: independent ROCm correctness reviewer (Review A of three parallel reviews)
- Date: 2026-10-26
- Tree under review: `/home/amd/Desktop/YuE2/upstream/sglang-merge`, branch
  `integration/yue2-sglang-gfx1151-merge-ready`, HEAD `bcb496ab9`, plus the
  uncommitted 4-file working-tree overlay (fused_moe.py sgl_kernel guard; 3
  quark/aiter guards).
- Method: source reading (`python/sglang/srt/models/yue2/*`, kernels/ops,
  multimodal_gen pipeline stages), `git show def437fb` comparison, and live
  probes on the actual gfx1151 host (Radeon 8060S, torch 2.12.0+rocm7.14.1,
  `torch.version.cuda=None`, `torch.version.hip=7.14.60850`,
  `get_device_capability() == (11,5)`) using `environments/yue2` with
  `PYTHONPATH=<merge>/python`. No network used.

Live host facts established during this review (merge tree, fresh process):

```
fa3_available()            = False   (shared FA op skipped on HIP)
deepselect_runnable()      = False
fast_sampler_available()   = False
batched_ar_enabled()       = False
is_deepselect_supported()  = False   (cap (11,5) not in ((9,0),(10,0),(10,3)))
sgl_kernel                 = absent from venv (ImportError)
aiter                      = absent from venv (ImportError)
```

These match the claimed E2E dispatch (capability gates alone, no env disables,
no HSA_OVERRIDE).

---

## 1. The four capability gates

### 1.1 `fastpath.deepselect_runnable()` — PASS

`python/sglang/srt/models/yue2/fastpath.py:51-70`. Loads the in-tree backend
(`sglang.kernels.ops.deep_select`), then probes `is_deepselect_supported()`;
probe errors fail safe to `False` (`except Exception: return False`).
`fast_sampler_available()` (line 73-76) is env-check AND delegate — no
independent platform sniffing anywhere in the file. This is a real capability
probe, not a string sniff.

One latent hole (P2-A below): the pip-fallback branch (line 66-67,
`probe is None → torch.cuda.is_available()`) returns True on any HIP build.

### 1.2 `song._generate_song_tokens_step_graph` gate — PASS

`python/sglang/srt/models/yue2/song.py:51-69` attempts the step graph only
when `cfg_scale == 1`, `cot != "off"`, env enabled, and `session.device.type
== "cuda"` (HIP maps to `"cuda"`, so the attempt is made and then rejected by
capability — the correct order). The rejection at `song.py:119-126`
(`_StepGraphUnavailable`) happens **before** any session mutation: both the
backend-missing check (line 119) and `deepselect_runnable()` (line 121)
precede `GraphSampler` creation (line 132) and `session.reopen` (line 149).
The caller catches only `_StepGraphUnavailable` and falls to
`_generate_song_tokens_looped` (line 71-83), which uses
`fast_sampler_available()` (line 300) → `sampler=None` → the reference
`distribution()`/`torch.multinomial` decode loop. No partial-state hazard.

### 1.3 `fa3` gate — PASS

`python/sglang/srt/models/yue2/fa3.py:32`: shared `flash_attn_varlen_func`
is only loaded when `torch.version.hip is None` (plus the env check). This is
a torch-build identity check — the semantically correct discriminator here,
because the shared op's *dispatch* is CUDA-only regardless of GPU capability;
see P3-C for the (acceptable) conservatism. The alternative
(`hasattr` probing the sglang op) would wrongly enable it on HIP since the
op imports fine on this host (verified: the ungated author tree at
`upstream/sglang` imports it successfully on gfx1151 — that tree's
`fa3_available()` returned True in my probe, demonstrating exactly the
call-time-failure trap the gate exists to avoid).

### 1.4 `batched.batched_ar_enabled()` — PASS

`python/sglang/srt/models/yue2/batched.py:40-46`: env check + delegate to
`deepselect_runnable()`. Consumer `Yue2ARStage.run_grouped_requests`
(`multimodal_gen/.../yue2/ar.py:160-161`) routes to per-request `forward`
when disabled. Pooled `GraphAR` sessions (pure PyTorch CUDA-graph) remain
enabled, as intended — validated by E2E.

### 1.5 Self-gating CUDA-only paths outside the four named gates — PASS

- **FUSED_DECODE**: `cuda_graph.py:262-274` — `use_fused_kernels` requires
  env + `device.type == "cuda"` + bf16/fp16 + `not fuse_projections` +
  `import sgl_kernel` in try/except → False on this host (no wheel). The
  fused body (`_decode_fused`, lines 383-492) is then unreachable and the
  reference `_decode` runs. (See P2-B for importability-vs-runnability.)
- **FAST_NAR / velocity graphs**: `nar_fast.py:23-38` `_sgl_kernel()` → None
  on this host; `SessionNAR.__init__` (line 72-81) and `BatchedSessionNAR`
  (line 267-269) raise `ValueError`, which `Yue2NARStage.forward` catches
  (`multimodal_gen/.../yue2/nar.py:142-143`) and falls back to the reference
  `nar.synthesize` (CachedNAR, plain SDPA). The batched NAR pre-checks
  `_sgl_kernel() is None` → `_NarBatchUnsupported` → per-request
  (`nar.py:43-46`). `_VelocityGraph` capture (`nar_fast.py:483-485`) is only
  reachable after `SessionNAR.__init__` succeeded, so no capture is attempted
  without sgl_kernel.
- Grepped the whole yue2 tree for `sgl_kernel|flash_attn|flashinfer|deep_select`:
  all hits are the gated sites above (`cuda_graph.py:270/391/403/419/474/478/484`,
  `nar_fast.py`, `fa3.py`, `fastpath.py`). No `platform` string sniffing, no
  `get_device_name` parsing, no `/proc` reads anywhere in the yue2 package.
- CUDA graphs themselves (`torch.cuda.CUDAGraph`) are used on ROCm by the
  *reference* looped path (pooled `GraphAR` sessions) and validated by E2E —
  the gates exclude only the CUDA-only kernels captured inside them.

### 1.6 Comparison with `def437fb` — PASS, semantically identical

`git show def437fb` (fork PR #1) compared function-by-function (AST unparsed):
`deepselect_runnable`, `fast_sampler_available`, `_load_varlen`,
`batched_ar_enabled`, and the step-graph prelude are textually/semantically
identical to the merged tree; the only differences are the ruff-format commit
(`5dc9b33a8`) reflows. The merge of upstream main did not weaken any gate.

---

## 2. Hardware capability detection (`is_deepselect_supported`)

`python/sglang/kernels/ops/deep_select.py:169-190` — correct and fail-safe:

1. Line 171: `if torch.version.cuda is None or not torch.cuda.is_available():
   return False` — any HIP build of torch returns False immediately, so ROCm
   devices can never pass the probe regardless of how capability is mapped.
2. Lines 173-188: normalizes the device, rejects non-`cuda` types, and
   requires `get_device_capability(device) in _SUPPORTED_CAPABILITIES`
   (`((9,0),(10,0),(10,3))`, line 25).
3. Lines 189-190: `except (RuntimeError, TypeError, ValueError): return
   False` — detection errors fail safe.

Live on gfx1151: capability reports `(11,5)` → False (probe result confirmed
above). A MI300X (gfx942 → (9,4)) would also get False — conservative
(disables the fast sampler there too); acceptable for correctness.

**Defense in depth**: even if a caller bypassed every gate, `topk()` itself
re-checks capability at launch time — `deep_select.py:246-249`
(`raise RuntimeError(f"DeepSelect does not support SM{major}{minor}")`) plus
`input.device.type != "cuda"` and dtype/shape validation (lines 226-243).
There is no path by which a ROCm tensor reaches the JIT kernel launch through
this module.

The sibling `python/sglang/kernels/ops/attention/deep_select.py` (DSV4
indexer, pre-existing upstream main — provenance `9d68ecce2`, not the YuE2
PR) has the same `torch.version.cuda is None` short-circuit in
`is_deep_select_supported()` (line 200-205) and its gated consumer
(`dsv4/v41_indexer/full_topk.py:50-51`) uses it. One ungated caller exists
(`dsv4/v41_indexer/scoring.py:292` calls `topk` directly for bf16); it is
unreachable from YuE2 and pre-existing on main — P3-E, informational.

---

## 3. Overlay (4 uncommitted files) — memory safety of None bindings

All four files import cleanly on gfx1151 with the overlay (live-verified);
`sgl_kernel` and `aiter` are both absent from the venv, so every guarded
import binds None:

| File | None-bound symbol(s) | Deref sites | YuE2-reachable? |
|---|---|---|---|
| `layers/moe/moe_runner/triton_utils/fused_moe.py:72-82` | `gelu_and_mul`, `gelu_tanh_and_mul`, `silu_and_mul` | `fused_experts` activation branches (lines 795, 808, 837-843) | No — YuE2 is dense bf16, no MoE; deref would raise loud `TypeError` for a MoE model |
| `layers/quantization/quark/schemes/quark_w4a4_mxfp4.py:170-189` | 7 aiter `_orig` fns + `shuffle_weight` | custom-op wrapper bodies (lines 198, 225, 248, 273, 302, 346) and weight-load (line 467) — call-time only | No — YuE2 loads bf16 via its own loader; `QuarkW4A4MXFP4` scheme never instantiated; `direct_register_custom_op` registration does not invoke bodies |
| `layers/quantization/quark/schemes/quark_w4a4_mxfp4_moe.py:118-126` | `dynamic_mxfp4_quant` | guarded by existing `if dynamic_mxfp4_quant is None` checks (lines 643, 716, 829) that raise informative errors | No |
| `layers/quantization/quark_int4fp8_moe.py:29-35` | `shuffle_weight` | `process_weights_after_loading` (lines 368, 373) only | No |

Cross-module imports of these modules pull only classes
(`quantization/__init__.py:45` → `QuarkInt4Fp8Config`;
`quark/schemes/__init__.py:4` → `QuarkW4A4MXFP4`), never the None-bound
functions. **Conclusion: on the YuE2 execution path (bf16, dense, no
quantization) no None is dereferenced; the bindings exist only so that
import-time discovery of unrelated quant/MoE code does not kill server boot
on non-CDNA ROCm hosts.** Behavior for models that *do* need those ops is
fail-loud (TypeError at call time), strictly better than the pre-overlay
boot failure. Overlay appropriately excluded from the branch and destined
for separate main PRs.

---

## 4. Fallback execution (`fa3` on HIP)

`fa3.py:72-84` calls `torch.ops.aten._flash_attention_forward(q, k, v,
cu_seqlens_q, cu_seqlens_k, max_q, max_k, 0.0, False, False,
seqused_k=seqused_k)[0]`. Verified against the installed build's schema:

```
aten::_flash_attention_forward(Tensor query, Tensor key, Tensor value,
  Tensor? cum_seq_q, Tensor? cum_seq_k, SymInt max_q, SymInt max_k,
  float dropout_p, bool is_causal, bool return_debug_mask, *, float? scale,
  ..., Tensor? seqused_k=None, ...) -> (Tensor output, ...)
```

— argument order, `is_causal=False`, `return_debug_mask=False`, keyword
`seqused_k`, and `[0]` output indexing all match. Numerically verified on
gfx1151 (this review, GQA 8:2, head_dim 96, per-row `seqused_k=[5,12,8]`,
bf16): max abs error **0.0048** vs an fp32 SDPA reference — i.e. bf16-level
agreement, each row attends exactly its `seqused_k` prefix and GQA expands
correctly. Contiguity at the two call sites is sound: `q[:, 0]` on
`[B,1,HQ,HD]` and `keys.view(-1,HKV,HD)` are contiguous (`cuda_graph.py:338-347`,
`442-451`); `nar_fast.py` slices contiguous `qkv` buffers and `keys[0]`.
The `flash` backend selection in `GraphAR.__init__` (`cuda_graph.py:168-176`)
is itself a runtime probe (`hasattr(torch.ops.aten,
"_flash_attention_forward")` + `"seqused_k" in schema`), not a platform
sniff.

---

## 5. Audio output integrity

Walked the full path: NAR solve → CPU fp32 latents with hard
`torch.isfinite` guards (`nar_fast.py:250-254`, `nar.py:264-268`) → VAE stage
`_latent` re-checks finite and forces fp32 CPU `[1,64,T]`
(`multimodal_gen/.../yue2/vae.py:33-38`) → `decode_tiled` runs the decoder in
fp32 with autocast disabled (`modeling_vae.py:682-685`), input finiteness
re-checked (`modeling_vae.py:638-639`), tile crops copy exactly into a
preallocated CPU fp32 buffer (lines 735-751) → `sf.write(path,
audio.squeeze(0).cpu().numpy().transpose(1,0), sample_rate)` (vae.py:60-62).
No silent-corruption vector found:

- Every dtype cast is explicit and fp32 at the audio boundary; noise draws
  are CPU fp32 with CPU generators (`nar.py:55-58`), so stream/RNG platform
  differences cannot alter the noise.
- Stereo interleaving is correct (`[2,S]` → transpose → `[S,2]` frames).
- soundfile 0.13.1 with float32 data + format WAV defaults to **PCM_16**
  (verified live) — consistent with the E2E "16-bit WAV" evidence. Float
  values beyond ±1 hard-clip at write time (decode output is unclamped by
  design, `modeling_vae.py:680`); that is reference-faithful, not ROCm
  corruption — see P3-D.
- Non-contiguous tensor risks in the executed paths: none found (the only
  `.view()` on a strided slice, `cuda_graph.py:436-438`, is in the
  sgl_kernel fused path, unreachable on this host; the executed eager
  `_decode` and NAR reference use `project_qkv`/SDPA on contiguous tensors).

---

## Findings

### P0 — none

### P1 — none

### P2-A: pip-fallback branch of `deepselect_runnable()` would enable the fast sampler on ROCm
`python/sglang/srt/models/yue2/fastpath.py:66-67` — when the loaded backend
lacks the probe (pip `deep_select`), the fallback is
`torch.cuda.is_available()`, which is **True on HIP builds**. Preconditions:
in-tree `sglang.kernels.ops.deep_select` import fails AND pip `deep_select`
is installed. Then `FastSampler`/step-graph activate on ROCm and fail at
first `backend.topk` (loud crash, potentially inside graph capture for the
step-graph path — an uncaught RuntimeError, request-killing rather than
silent). Not reachable in the validated environment (in-tree backend imports
fine, probe returns False — verified live). Exact fix (one line):

```python
if probe is None:
    return torch.version.hip is None and torch.cuda.is_available()
```

(or add a probe to the pip package). P2: must-fix quality hole in the
"capability, not platform" story, but requires a pathological setup to
trigger and fails loudly when it does.

### P2-B: `import sgl_kernel` success is treated as runnability for the fused decode/NAR kernels
`python/sglang/srt/models/yue2/cuda_graph.py:269-274` (FUSED_DECODE) and
`nar_fast.py:23-38` (fast NAR / velocity graphs). On a ROCm host with a
CDNA-targeted sgl-kernel wheel installed (e.g. an MI300X user), `import
sgl_kernel` succeeds but `rmsnorm` / `fused_add_rmsnorm` /
`fused_qk_norm_rope` / `silu_and_mul` may be missing (ROCm builds export a
subset) or gfx-mismatched → AttributeError/launch failure inside CUDA-graph
capture → request failure rather than fallback. The validated gfx1151 host
has no wheel, so this is untriggered there. Exact fix: after the import,
require all four ops before enabling:

```python
import sgl_kernel
self.use_fused_kernels = all(
    hasattr(sgl_kernel, op)
    for op in ("rmsnorm", "fused_add_rmsnorm", "fused_qk_norm_rope", "silu_and_mul")
)
```

(and the same predicate in `nar_fast._sgl_kernel()`). Failures then route to
the reference paths instead of crashing. Could be a follow-up PR; not a
gfx1151 blocker.

### P3-A: `GraphAR` "auto" can select a `cudnn` attention backend that does not exist on ROCm
`cuda_graph.py:184-187` falls back to `"cudnn"` when
`torch.backends.cudnn.is_available()` — True on ROCm builds (MIOpen exposes
the cuDNN API) — and the `cudnn` branch (lines 348-360) forces
`SDPBackend.CUDNN_ATTENTION`, unsupported on many ROCm builds; failure would
occur inside graph capture. Unreachable on the pinned torch (aten
`_flash_attention_forward` exists, verified — auto always picks `flash`),
but the guard is coincidental. Suggest excluding `cudnn` when
`torch.version.hip is not None`.

### P3-B: fast-NAR tail feed runs before the fast path's availability check
`nar_fast.py:576-582` feeds the unfed codec tail + `MUSIC_END` into the
session **before** `SessionNAR.__init__` raises ValueError (sgl_kernel
missing) and the stage falls back to reference NAR. Output correctness is
unaffected (reference NAR re-prefills from tokens; the pooled session is
`reopen`ed with position/KV-slot overwrite semantics, `cuda_graph.py:641-679`)
— but every ROCm request pays a wasted tail feed of decode steps. Move the
`_sgl_kernel()` check above the feed loop, or hoist it to the stage.

### P3-C: `fa3` HIP gate is torch-build-level, not per-device capability
`fa3.py:32` disables the shared FA op on *all* HIP devices, including future
Instinct parts where sglang FA kernels may someday ship. Correct and
validated today (the sglang op is CUDA-only); revisit if ROCm FA lands
upstream. Documented in the module docstring.

### P3-D: WAV subtype not pinned at `sf.write`
`vae.py:60-62` relies on soundfile's default (PCM_16 for float32 input,
verified on soundfile 0.13.1 — matches the E2E evidence). Pin
`subtype="PCM_16"` explicitly so a future soundfile default change cannot
alter output format, and note that unclamped float output hard-clips at ±1
on quantization (reference-faithful behavior).

### P3-E (informational, outside YuE2 blast radius): ungated deep_select consumer on main
`python/sglang/srt/layers/attention/dsv4/v41_indexer/scoring.py:292` calls
`kernels/ops/attention/deep_select.topk` directly for bf16 logits with no
`is_deep_select_supported()` check (unlike `full_topk.py:50-51`), and
`_launch_topk_impl` has no launch-time capability guard. Pre-existing
upstream main code (DSV4 path, commit 9d68ecce2), unreachable from YuE2;
worth a separate upstream issue.

### P3-F (operational, not a code defect): the `yue2` venv's editable install targets the ungated author tree
`environments/yue2` site-packages' editable finder resolves to
`/home/amd/Desktop/YuE2/upstream/sglang` (author head `ced0ef7d`, **no ROCm
gates**), not the merge tree. The E2E evidence documents that
`PYTHONPATH=<integration>/python` overrides the finder (and PYTHONPATH does
take precedence); this review independently reproduced the hazard — without
PYTHONPATH, `fa3_available()` returns True on gfx1151. A wrong-tree launch
fails loudly at first attention (the docstring's documented call-time
failure), not silently, but any future validation run must keep setting
PYTHONPATH (or repoint the editable install) or it will silently test the
wrong code.

---

## Verdict

All four capability gates key on genuine capability probes
(`is_deepselect_supported` / `deepselect_runnable` / `torch.version.hip` /
`sgl_kernel` importability) with no platform string sniffing; the fallbacks
are the validated reference paths; the launch-time re-check in
`deep_select.topk` makes CUDA-kernel leakage from ROCm impossible through
the YuE2 tree; the overlay's None bindings are provably not dereferenced on
the bf16/no-MoE/no-quant YuE2 path; and the aten varlen fallback was
re-verified numerically on hardware in this review. No P0/P1. Two P2s are
latent, loud-failure robustness holes in unlikely configurations, both with
one-line fixes suitable for follow-up.

**VERDICT: PASS-WITH-P2s**
