# SGLang PR #42106 — Minimal ROCm Handoff for the Author (2026-10-13)

PR: https://github.com/sgl-project/sglang/pull/42106 (`Add yue2`)
State refreshed 2026-10-13: OPEN, **CONFLICTING with main**, head `add_yue2`
@ ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f (no movement since 2026-10-04).
We will NOT force-rebase or rewrite this PR; nothing below requires us to.

## Where ROCm breaks today (verified on W7900/gfx1100, ROCm 7.14.1)

Your yue2 files import fine on ROCm, but four hot paths conflate
"importable" with "runnable":

1. `srt/models/yue2/song.py:37-39` — step-graph condition uses
   `session.device.type=="cuda"`, which is TRUE on HIP; the graph capture
   then dies inside DeepSelect `topk()`.
2. `srt/models/yue2/fastpath.py:50-58` — `fast_sampler_available()` keys on
   `torch.cuda.is_available()` (True on HIP) and only checks the import.
3. `srt/models/yue2/fa3.py:28` — `_load_varlen()` is env-gated only; the
   shared wrapper imports but its kernels are CUDA-only → fails mid-forward.
4. `srt/models/yue2/batched.py:38-39` — `batched_ar_enabled()` admits ROCm
   into the BatchedGraphSampler, which needs DeepSelect.

## Recommended fix shape (3 + 1 tiny guards, ≤10 lines each)

Key everything on YOUR OWN capability check —
`sglang.kernels.ops.deep_select.is_deepselect_supported()` (deep_select.py:169,
already in your PR; returns False on ROCm and on unsupported compute
capabilities). No platform sniffing, no second architecture:

1. `song.py`, in `_generate_song_tokens_step_graph` after the existing
   backend check (~line 81): raise `_StepGraphUnavailable` when
   `not is_deepselect_supported()`.
2. `fastpath.py::fast_sampler_available()`: after the
   `torch.cuda.is_available()` check, return `is_deepselect_supported()`.
3. `fa3.py::varlen_attention()`: wrap the `varlen(...)` call in try/except
   and fall through to `torch.ops.aten._flash_attention_forward` (strictly
   more general: also rescues flash_attn-less CUDA hosts). Alternative:
   gate `_load_varlen()` with `and not is_hip()`.
4. (polish) `batched.py::batched_ar_enabled()` → consult
   `fast_sampler_available()`.

We validated exactly this shape end-to-end on the SGLang-Omni port of your
code (W7900, real `POST /v1/audio/speech`, 48 kHz stereo WAV HTTP 200, and a
384-candidate WildSongBench run currently finishing) — see
yiakwy-xpu-ml-framework-team/sglang-omni PR #1 for the five-file omni
equivalent of guards 1-4.

## Notes

- Capability gating also disables these paths on pre-Hopper CUDA (SM 8.x)
  hosts that would crash the same way today — a net improvement, but your
  call on semantics.
- The quantization/memory-cache import fixes we needed locally
  (quark/kvcacheio, evidence patches 0001-0003/0008) touch base-branch files
  your PR does not modify. They belong in independent `main` PRs, NOT inside
  #42106. No reproducer inside the YuE2 path requires them once guards 1-4
  are in.
- `cudnn`-disable has no equivalent need: your `cuda_graph.py` auto-backend
  resolves to "flash" on ROCm and the cudnn branch is never auto-selected.
- If you have already added equivalent gates while resolving the conflicts,
  drop ours as duplicates — nothing else conflicts.

## Suggested next action for the author

Resolve the `main` conflicts on `add_yue2`, then add guards 1-4 as a small
follow-up commit (happy to send the exact diff as a patch file on request —
we deliberately did not open a public contribution on this PR without your
agreement on the route).

State: SGLANG_42106_HANDOFF_READY (analysis cross-verified byte-identical
local mirror vs PR refs; see phase7_sglang_mapping.md for the full matrix).
