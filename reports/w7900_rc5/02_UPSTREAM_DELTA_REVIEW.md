# RC5 M2.1 — Latest Upstream Delta Review (YuE2 SGLang)

Reviewer: independent (RC5 mission). Method: API-verified heads, `git` tree
comparison, line-level reading of every changed file and of the platform
code paths, real-GPU bring-up on the W7900D. No NVIDIA hardware was available:
CUDA statements below are **code-review or CPU-dispatch-test statements**.

## 1. Baselines (verified 2026-11-24 through the GitHub API)

| | commit | role |
|---|---|---|
| Historical (RC4 / frozen Arm B) | `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` | 3rd of 5 PR commits |
| ROCm integration | `2a816358de5dd76da7394348022d0f53f2cdcc99` (2026-11-22) | capability gates |
| **Current PR #42106 head (frozen for RC5)** | `c67d541a40f8bf851e9fc1e925f5316638838cd6` (2026-11-23) | DGX Spark GB10 verification |

PR #42106 (`Add yue2`, head `yiakwy-xpu-ml-framework-team:AMD-sglang-benchmark-fork@add_yue2`,
base `main`): open, not draft, 5 commits, 37 files, +7150/−0. `refs/pull/42106/merge`
was never used. The head was re-checked at freeze time and had not moved
(`02_EFFECTIVE_RUNTIME_MANIFEST.json`: `head_is_verified_pr_head: true`).

`python/` differs between the historical and the current head in **exactly
five YuE2 files** (plus two new test files):

| commit | batched.py | fa3.py | fastpath.py | song.py | stages/yue2/ar.py |
|---|---|---|---|---|---|
| 2a816358 | +7 −2 | +6 −2 | +20 −4 | +7 −1 | — |
| c67d541a | +1 −4 | +24 −6 | +6 −10 | +0 −4 | +1 −1 |

Nothing under `python/sglang/srt/models/yue2/{modeling_yue2,nar,cuda_graph,sampling,protocol,storage,tokenization_yue2}.py`,
`modeling_vae.py`, the NAR / VAE / artifact stages, the loader or the pipeline
changed. **The generation math is untouched by the delta; it is dispatch only.**

## 2. What the two commits change

* `fastpath.deepselect_runnable()` — runnable, not merely importable: asks the
  loaded backend's `is_deepselect_supported()`; a backend without that probe
  is assumed CUDA-only (`torch.version.hip is None and torch.cuda.is_available()`);
  any exception → `False` (fail safe to the reference sampler).
  `fast_sampler_available()` now delegates to it.
* `song.py` — the fused decode+sample step graph raises `_StepGraphUnavailable`
  *before* graph capture when the kernel cannot run; requests take the looped
  reference AR path.
* `fa3._shared_fa3_usable()` — on HIP the shared op is never loaded (it
  imports, then fails at call time with CUDA-only kernels); on CUDA only for
  compute capability `major == 9`. Everything else uses the native ATen
  varlen FlashAttention, which honours `seqused_k` / GQA.
* `batched.batched_ar_enabled()` — env flag **and** `deepselect_runnable()`.
* `stages/yue2/ar.py` — `use_fast_sampler=None` (auto) instead of `True`
  for the non-legacy path.

## 3. Item-by-item (mission list), ROCm gfx1100 + torch 2.12.0+rocm7.14.1

| Area | Code at c67d541a | Behaviour on this GPU | Evidence |
|---|---|---|---|
| AR decode | `GraphAR` session: HIP graph capture, reference sampler | **works**; every pilot candidate reports `execution=cuda_graph, sampler=reference` | `plan.json` of 12/12 pilot candidates (journal `termination`) |
| AR graph path | `torch.cuda.CUDAGraph()`; fused `_decode_fused` behind `try: import sgl_kernel` | graph on; fused kernels off (`ImportError`) | served with no `SGLANG_YUE2_*` override |
| FlashAttention | `fa3.varlen_attention`: shared op only if `_shared_fa3_usable()` | shared op skipped on HIP → `aten._flash_attention_forward` with `seqused_k` | `attention=flash` in 12/12 plan.json; probe: FLASH vs MATH max abs diff 0.0078 |
| SDPA | explicit `cudnn` / `sdpa` fallbacks in GraphAR; public SDPA in the NAR reference | public SDPA (FLASH / MATH) functional | `00_ENVIRONMENT` probe; NAR ran on 12/12 |
| DeepSelect | CUDA-only JIT (SM 9.0/10.0/10.3) | gated off natively | author tests + pilot |
| top-k sampling | reference pure-torch sampler | reference | `sampler=reference` |
| NAR flow matching | reference `nar.synthesize` (32 midpoint steps, context 24576); fast path needs `sgl_kernel` | reference path (`yue2_nar_fast` unset) | NAR 26–97 s per candidate |
| VAE decode | `decode_tiled` in fp32, core 1024 / halo 16, CPU output | **works** (55–243 s per song) | FLAC 48 kHz stereo, finite |
| distributed / device gates | `yue2_parallel.py`: plain `torch.distributed` helpers | neutral; unused at TP=1 | code review |
| sgl-kernel / flashinfer | absent on ROCm | lazy loaders return `None`; import guards needed elsewhere (§5 F1/F2) | `rc5-0001-0003-0008` patch |
| HTTP generation API | `POST /v1/audio/generations` (+ `/music/` alias) | **works**; `yue2_timing`, `yue2_stage_seconds`, `yue2_nar_fast` are `null` at this head | §5 F4 |
| artifact exporter | plan / semantic / latent / prefix / abc_tokens / request | works; `audio.flac`, `config.json`, `result.json`, `score.abc` come from `finalize_candidate.py` | official `verify_result` + `prepare_inputs` 12/12 |
| scheduler | `sgl_diffusion::scheduler` worker | alive, 100 % GPU during a song; idle busy-loop (RC4.1 finding) is upstream scheduler code, not in this PR | M4 report |

## 4. Reproduction evidence

* **Deterministic seed:** the same candidate generated twice (two server
  sessions) is byte-identical in `audio.flac`, `semantic.npy`, `latent.npy`,
  `prefix.npy`, `abc_tokens.npy`, `score.abc`.
* **Latest head == historical head on real output:** all 12 pre-registered
  pilot candidates are **byte-identical (`audio.flac` SHA256)** to the frozen
  historical Arm B manifest (`evidence/publication/armB_campaign/candidate_manifest.json`)
  — durations 12/12, truncation flags 12/12. The upstream delta therefore
  does not alter ROCm generation output (hypothesis H8 of the PER study is
  refuted for this hardware).
* **Author dispatch tests** (`test/srt/models/test_yue2_platform_gates.py`) on
  this host: 19 passed, 2 failed — both failures are host assumptions of the
  tests, not code defects (§5 F5).

## 5. Findings for the author (not fixed in the frozen tree unless stated)

| id | finding | impact | RC5 handling |
|---|---|---|---|
| F1 | `quark/schemes/quark_w4a4_mxfp4.py`, `…_moe.py`, `quark_int4fp8_moe.py` import `aiter` unconditionally under `_is_hip` | on ROCm without Instinct `aiter`, `is_registered_diffusion_model_path()` raises `ImportError`, is swallowed, the CLI falls back to the LLM backend: `sglang serve: error: unrecognized arguments: --num-gpus …` (RC5-REPRO-2) | minimal import guards (historical 0001–0003, byte-identical) |
| F2 | `mem_cache/{hisparse_memory_pool,memory_pool_host,pool_host/mha}.py` import `sgl_kernel.kvcacheio` at module level under `_is_hip` | serving import chain crashes without `sgl_kernel` (RC5-REPRO-3) | minimal import guards (historical 0008, byte-identical) |
| F3 | `Yue2VAEDecodeStage._finish` writes the WAV with `sf.write(path, audio, sr)` → soundfile default **PCM_16**; the official `yue2-infer` writes `audio.flac` PCM_24 from float | the PR's audio is quantised to 16 bit (and clipped) before any repack; measured: every sample on the 1/32768 grid | not patched (no failure; main run stays pure-upstream); single-factor ASR sensitivity experiment in M6 (H7) |
| F4 | HTTP response fields `yue2_timing`, `yue2_stage_seconds`, `yue2_nar_fast` are always `null` (stages set `yue2_*` keys on `batch.extra`, the route reads `result.extra`) | clients cannot see stage timings | driver reads exact stage seconds from the server log |
| F5 | `test_pip_backend_without_probe_keeps_original_check` and `test_cuda_shared_fa_op_dispatch_unchanged` do not simulate `torch.version.hip` / `get_device_capability()` | 2/21 fail on any ROCm or non-SM90 host | recorded; test-only |
| F6 | `_shared_fa3_usable()` keeps the shared op only for `major == 9`, while the commit message says NVIDIA behaviour is unchanged on 9.0/10.0/10.3 | SM100/SM103 now use ATen varlen instead of the shared op | question for the author |
| F7 | comment "Torch 2.10 is pinned by the package"; `pyproject.toml` pins `torch==2.14.1` | stale comment | none |

## 6. Conclusion

The latest upstream head is usable on ROCm **with two small import-guard
patches and no capability override**: the author's own gates select the
reference / ATen paths that the historical operator flags used to force.
Output equals the historical frozen campaign bit for bit. The remaining
deviations from the official pipeline are the artifact exporter's 16-bit WAV
(F3) and the missing response timings (F4).
