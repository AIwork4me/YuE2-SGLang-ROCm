# 02 — Original SGLang YuE2 Real GPU E2E on gfx1151 (2026-10-26)

Tree under test: **`integration/yue2-sglang-gfx1151-merge-ready` @ `bcb496ab9`**
(AIwork4me/sglang fork; = author `add_yue2` `ced0ef7d` + ROCm PR `def437fb` +
lint `1a9f2d92` + latest main `5ef99013a` + loader-path fix + format fixup)

Host: Ryzen AI MAX+ PRO 395, Radeon 8060S (gfx1151), 32 GiB VRAM, ROCm 7.2.1
host / torch 2.12.0+rocm7.14.1, venv `environments/yue2` with
`PYTHONPATH=<integration>/python` (verified the editable-install finder is
overridden; venv itself untouched).

## Serving configuration (verified against the checked-out commit)

`scripts/serve_yue2_integration.sh` (archived in evidence):

```
sglang serve --model-type diffusion --model-path models/YuE2-3B \
  --host 127.0.0.1 --port 30065 --num-gpus 1 \
  --ulysses-degree 1 --ring-degree 1 --warmup-mode off
```

Two command corrections were required vs the historical benchmark recipe
(mission: "verify those commands against the checked-out commit"):

1. Current main requires **`--model-type diffusion`** to select the
   multimodal arg parser (`--num-gpus/--ulysses-degree/...` are rejected by
   the default LLM `serve` parser otherwise).
2. `http_server.py`'s YuE2 route loader still resolved
   `experimental/yue2/http_api.py` after main flattened `experimental/` —
   fixed in commit `bcb496ab9` (otherwise `/v1/audio/generations` would
   silently never register).

**Environment proof (mission requirement):** the server process environment
(`/proc/<pid>/environ`) contains only `SGLANG_YUE2_SESSION=1`,
`SGLANG_YUE2_GRAPH_POOL=1` (both enabling, validated accelerations) and
`SGLANG_YUE2_VAE_DIR`. **None of the disable variables
(`FAST_SAMPLER`, `STEP_GRAPH`, `FA3`, `BATCHED_AR`, `FUSED_DECODE`,
`FAST_NAR`) is set, and `HSA_OVERRIDE_GFX_VERSION` is unset.** On this
device the un-gated paths crash inside DeepSelect/graph capture (documented
in prior missions); successful completion therefore proves the `def437fb`
capability gates selected the working reference paths automatically.

## ROCm host-boot overlay (kept OUT of the integration branch)

Upstream main HEAD is import-broken on HIP hosts without CUDA wheels — two
independent of YuE2:

| File | Unconditional import | Overlay guard |
|---|---|---|
| `srt/layers/moe/moe_runner/triton_utils/fused_moe.py:73` | `from sgl_kernel import gelu_and_mul…` (in `elif _is_hip:`) | try/except → None bindings |
| `srt/layers/quantization/quark/schemes/quark_w4a4_mxfp4.py:163` | 7× `aiter` imports (in `if _is_hip:`) | try/except → None bindings |
| `srt/layers/quantization/quark/schemes/quark_w4a4_mxfp4_moe.py:118` | `aiter` import | try/except → None |
| `srt/layers/quantization/quark_int4fp8_moe.py:29` | `aiter` import | try/except → None |

Full diff: `reports/merge_readiness/patches/sglang_main_rocm_host_boot_overlay.patch`
(+49/−14, 4 files). These extend the same guard shape as the proven
benchmark-era patches 0001–0005 (quark/sgl_kernel equivalents) to main's
current code. sglang-kernel 0.4.10 on PyPI was tested and is CUDA-only
(`libnvrtc.so.13`), so no wheel can satisfy the import on this host. Each
guard only defers failure to call time on paths YuE2 (bf16, no MoE, no
quark) never executes. **Recommended as independent upstream `main` PRs —
not part of the YuE2 PR** (consistent with the standing author handoff
policy for base-branch fixes).

## Test results

### Test A — model loading — PASS

- Server: FastAPI up on 127.0.0.1:30065; log line
  `Using pipeline from model_index.json: Yue2Pipeline`; `Pipeline
  instantiated`; `Worker 0: Initialized device, model, and distributed
  environment.`
- No unsupported CUDA-only kernel executed at startup; no missing model
  dependencies (benign discovery skips for unrelated pipelines pi05/wan).
- ROCm device detected (HIP torch stack; device `cuda`→gfx1151 mapping).

### Test B — short end-to-end — PASS

Request: style "soft pop, warm piano, gentle drums", 5 lyric lines, seed
831001, `semantic_max_tokens 1200`, `abc_max_tokens 512`, `ode_steps 32`,
`cot=full` (default) → exercises AR (CoT planning + semantic) → NAR → VAE →
WAV.

| Check | Observed |
|---|---|
| HTTP status | **200** (224.1 s wall) |
| WAV valid | yes — RIFF/PCM, 2 channels, 48 000 Hz, 16-bit |
| Duration | 47.00 s (2 255 936 frames) |
| Nonempty / finite | yes; `np.isfinite` true over all samples (no NaN/Inf) |
| Non-silent | peak 22 041, RMS 3 272, 94.2 % of samples >100 |
| Hidden model fallback | none — response produced by Yue2Pipeline on this server; response JSON `object: audio.generation`, 48 kHz |

Artifacts: `runs/merge_readiness/phase2_testB/` (WAV + response JSON).

### Test C — realistic inference configuration — PASS

Full-song payload (4 sections incl. bridge), seed 831001,
`semantic_max_tokens 10000`, `abc_max_tokens 4096`, `ode_steps 32`.

- HTTP **200**, 414.0 s wall
- WAV: 2 ch, 48 kHz, **112.12 s** (5 381 696 frames), 21.5 MiB
- finite; peak 27 124; RMS 4 213; 94.8 % non-silent

Artifacts: `runs/merge_readiness/phase2_testC/`. Sampling, attention
(session GraphAR + ATen flash via the HIP gate), NAR (per-request fallback)
and VAE all completed; peak VRAM within the 32 GiB APU budget (no OOM).

### Test D — dispatch and regression — PASS

`test/registered/unit/models/test_yue2_platform_gates.py`: **21/21 passed**
against this exact tree (run in Phase 1, on-device, venv + PYTHONPATH).
Positive/negative capability cases included; CUDA semantics preserved
(fake-backend positive cases assert the fast paths still engage when
DeepSelect is supported).

## Known gaps / honest notes

- `yue2_stage_seconds` / `peak_memory_mb` fields in the response are
  `null`/0.0 — instrumentation of the response object on this tree does not
  populate them; wall-clock times above are measured client-side.
- Audio quality parity with the H800 reference is **not claimed** — this
  mission validates the integrated tree executes correctly on gfx1151, not
  benchmark equivalence (the 384-candidate historical run covers that on the
  frozen benchmark tree).
- Full 384-candidate WildSongBench was intentionally NOT repeated.

Status: **Phase 2 PASS (A, B, C, D) on the integrated tree.**
