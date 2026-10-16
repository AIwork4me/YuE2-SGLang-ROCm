# ROCm FlashAttention-2 Compatibility Investigation for YuE2 — seqused_k Semantics

Phase-6 investigation, 2026-10-16, isolated probe process (no production
environment changes; no packages installed). Probe:
`bench/fa2_sequsedk_probe.py`; raw results: `evidence/omni_wsb/fa2_probe_results.json`.

## 1. Why this matters

YuE2's AR decode attends with a per-row effective KV length passed as
`seqused_k` (allocated KV slots hold garbage/future tokens; only each row's
completed prefix is visible — `sglang_omni/models/yue2/cuda_graph.py:236-244`).
Any attention backend that ignores `seqused_k` silently attends over unfilled
slots and produces wrong output.

## 2. SGLang dispatch findings (code inspection, sgl-src @ PR#42106 head)

1. `sglang/kernels/ops/attention/flash_attention.py::flash_attn_varlen_func`
   accepts `seqused_k` but only dispatches ver=3 (FA3) and ver=4; there is no
   ver=2 branch.
2. `flash_attention_v3.py:218-236`: when FA3 kernels are unavailable
   (e.g., ROCm), it falls back to the `flash_attn` package (FA2) — and the
   fallback DOES NOT forward `seqused_k` (nor `seqused_q`). It forwards only
   max_seqlen_q/k, softmax_scale, causal, window_size, softcap.
3. The Dao-AILab FA2 public `flash_attn_varlen_func` interface has no
   `seqused_k` parameter (the fallback's call signature is the full set of
   what FA2 accepts). Conclusion: enabling the shared FA path on ROCm today
   would silently drop YuE2's effective-KV semantics. DO NOT switch blindly —
   confirmed at source level.

## 3. Numerical probe results (ATen path — the currently validated route)

| Test | Case | max_abs_diff vs float64 ref | Verdict |
|---|---|---:|---|
| T1 | variable ragged rows [3,17,5,128,1], bf16, non-causal | 8.57e-3 (tol 2e-2) | PASS |
| T2 | seqused_k (25/32 of allocated) < allocated KV, bf16 | 7.30e-3 | PASS |
| T3 | NaN-poisoned padded KV tail with seqused_k cap | 0.0 (bitwise unchanged) | PASS |
| T4 | GQA HQ:HKV = 8:1, bf16 | 5.85e-3 | PASS |
| T7a | bf16 mixed ragged | 7.50e-3 | PASS |
| T7b | fp16 mixed ragged | 9.85e-4 | PASS |
| T8 | control: same call WITHOUT seqused_k differs by 1.59 | proves seqused_k is honored, not a no-op | PASS |
| Latency | ATen varlen, YuE2-AR-like shapes (bs 1-4 rows, KV 4k/16k, GQA 8:4, D=64, bf16) | p50 ≈ 0.068 ms/call | recorded |

Environment: AMD Radeon Pro W7900D (gfx1100), torch 2.12.0+rocm7.14.1.
The ATen ROCm flash backend accepts only fp16/bf16 (matches YuE2's bf16
compute); float32 inputs are rejected by the op itself.

## 4. Verdicts per candidate path

| Path | Verdict | Evidence |
|---|---|---|
| A. Native ROCm FA2 with correct KV packing | **BLOCKED** | No ROCm flash-attn build exists for this stack (torch 2.12+rocm7.14.1/gfx1100; flash_attn import unavailable in every environment). Even with a build: the public FA2 varlen API lacks seqused_k, so correctness requires re-packing K/V to per-row effective lengths before every decode step (full-KV copy per token) — a cost likely exceeding FA2's gain, and the current SGLang fallback drops seqused_k regardless. Prerequisites: FA2/aiter interface exposing per-row KV caps (or an upstream seqused_k forwarding fix), then re-run this probe against that build. |
| B. Supported AITER varlen backend | **BLOCKED** | aiter has no compatible build for gfx1100 / this ROCm 7.14.1 torch stack (targets MI-class APUs); installing incompatible aiter/Triton builds into the production benchmark environment is prohibited (and would invalidate the validated environment). |
| C. Validated ATen varlen fallback (status quo) | **PASS** | All 8 numerical tests pass (variable lengths; seqused_k < allocated; padded-KV NaN isolation; GQA; non-causal; multiple ragged rows; bf16/fp16; honoring control). End-to-end validity is independently established by the 384/384 WSB run scored with official metrics on this path. |

## 5. Recommendation

Keep path C (ATen) as the correctness-first default on ROCm — exactly what PR
#1 does today. If a ROCm FA2 build with a seqused_k-capable interface lands
(upstream Dao-AILab/AMD work), prepare a SEPARATE follow-up PR that (a) fixes
the FA3→FA2 fallback to forward seqused_k, (b) passes this probe suite
against the new build, and (c) only then benchmarks attention-kernel latency
and end-to-end impact. Do not fold this into the correctness-first ROCm PR
while the author is reviewing it. Attention-kernel share of YuE2 E2E on W7900
is small under ATen (AR stage ≈ 93.7% of E2E is dominated by decode loop
compute; measured varlen call p50 0.068 ms), so expected end-to-end gain from
an FA2 swap is bounded and must be proven, not assumed.
