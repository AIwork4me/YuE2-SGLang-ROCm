# SGLang-Omni add_yue2 ROCm handoff — 2026-10-13

## Submitted PR

- URL: https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1
- Title: fix(yue2): enable ROCm reference path without regressing CUDA fast paths
- Base: yiakwy-xpu-ml-framework-team/sglang-omni `add_yue2` @ 85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9
- Head: AIwork4me `fix/yue2-rocm-reference` @ 50c91c0 (single commit)
- State at filing: DRAFT — full Omni end-to-end ROCm smoke test pending a free
  GPU window on the W7900 (WildSongBench gfx1100 full run in progress); all
  dispatch-level tests and a real-GPU native-ATen varlen check already pass.

## Files and lines changed (Omni)

- sglang_omni/models/yue2/stages.py — factory accepts CUDA or ROCm;
  SGLANG_YUE2_BATCH_MAX_SIZE defaults to 1 on ROCm (NVIDIA default 4 kept).
- sglang_omni/models/yue2/song.py:39-45 — Step Graph bypassed on ROCm.
- sglang_omni/models/yue2/fastpath.py:75-80 — fast sampler off on ROCm.
- sglang_omni/models/yue2/fa3.py:32-33 — shared FA3 varlen op skipped on ROCm
  (native ATen path selected).
- tests/unit_test/models/test_yue2_platform_gates.py — 12 dispatch tests
  (all pass on the ROCm host; 11/12 fail on the unpatched base).

## Verification performed on gfx1100 (W7900D, torch 2.12.0+rocm7.14.1)

1. Platform facts: RocmSRTPlatform is_cuda()=False / is_rocm()=True /
   device_type="cuda"; torch.cuda.is_available()=True; deep_select and the
   shared flash_attn_varlen_func import fine despite CUDA-only kernels.
2. Patched gates evaluated live: fa3_available()=False,
   fast_sampler_available()=False, ROCMOmniPlatform resolved.
3. Real GPU run of patched fa3.varlen_attention (native ATen, bf16, GQA,
   seqused_k) — finite, correct shape, shared op inactive.
4. 12/12 unit tests + 37 model-capability tests green.
5. Independent review: APPROVE-WITH-NITS, zero P0/P1 (mutation-tested).

## Omni -> original SGLang (sgl-project/sglang PR #42106) mapping

| Omni change | Original SGLang path | Status |
|---|---|---|
| stages.py factory gate + ROCm batch default | none (Omni-only pipeline glue) | do NOT port; different lifecycle |
| song.py Step Graph gate | python/sglang/srt/models/yue2/song.py | already covered by local patch 0004 (is_deepselect_supported) |
| fastpath.py availability gate | python/sglang/srt/models/yue2/fastpath.py | already covered by local patch 0004 |
| fa3.py shared-op platform gate | python/sglang/srt/models/yue2/fa3.py | NOT gated upstream by default; needs the equivalent HIP guard so SGLANG_YUE2_FA3=0 is not required on Radeon |

Backport ask for #42106: add the HIP guard to fa3.py `_load_varlen` (mirror of
the Omni patch) so ROCm defaults to native ATen varlen attention. Everything
else the Omni PR needs already exists in the validated local patch series
(0001-0005, 0008) kept in this evidence repo.

## External prerequisites (documented, intentionally NOT in the Omni PR)

The pinned sglang checkout needs the local guards from
evidence-repo/patches (0001-0005 aiter/DeepSelect, 0008 kvcacheio) to import
cleanly on gfx1100. They are separate SGLang-side fixes and stay out of the
Omni YuE2 PR per the minimal-diff constraint.

## Reproduction pointers

- Isolated Omni env: /workspace/yue2-omni-pr/env-omni-rocm (AMD wheels
  torch[device-gfx1100]==2.12.0+rocm7.14.1 + torchvision 0.27.0 + torchaudio
  2.11.0; sglang from the pinned tarball with patches applied; sglang-omni
  editable from the author's add_yue2 + this patch).
- Staged smoke test: /workspace/yue2-omni-pr/smoke_test_omni_yue2_rocm.sh
  (refuses to run while run_wsb.py holds the GPU; validates 48 kHz stereo,
  finite samples, non-zero RMS). Results will be appended to the PR.

---

# Closure update — 2026-10-13 (merge readiness pass)

## Clean dependency verification (Phase 2 of closure mission)

Pristine upstream sglang (author's pinned tree, local ROCm guards stashed):

| import chain | result |
|---|---|
| sglang / sglang.srt.platforms / sglang_omni.cli / serve.launcher / pipeline stage workers / every models/yue2 module | PASS (gfx1100) |
| sglang.srt.layers.quantization chain | FAIL: module-level `aiter` import (quark_w4a4_mxfp4.py:86 et al.) |
| sglang.srt.mem_cache kvcacheio paths | FAIL: `sgl_kernel.kvcacheio` module-level imports |

Blocker classification: **B** (shared-infra module-level HIP imports assume
aiter/sgl_kernel exist) + **C** (no consumer-Radeon aiter/sgl_kernel builds).
**A (Omni YuE2 patch defect): none found.** The Omni YuE2 pipeline never
imports the failing chains (verified live via sys.modules audit by independent
reviewer #1): **no sglang patches are required for the Omni YuE2 path.** The
guards remain mandatory only for the original SGLang server (#42106) or other
Omni models that build a full sglang engine.

The isolated env now runs sglang PRISTINE; local guards preserved at
/workspace/yue2-omni-pr/sglang-local-patches.keep (git stash) for instant
restore if the e2e run surfaces a deeper blocker.

## Reviews (Phase 4)

- #1 ROCm runtime correctness: launch/import audit VERIFIED; runtime trace
  VERIFIED; smoke-script contract VERIFIED (raw WAV, request shape, /health).
  Findings fixed: script exit-code false-pass (P1), grep guard, literal \n,
  port hardcoding. Remaining accepted risk: native-ATen varlen under HIP graph
  capture inside GraphAR — de-risked by the prior real gfx1100 varlen run and
  by the original evidence runs (SESSION=1, FA3=0) of the same GraphAR code.
- #2 NVIDIA regression + minimal diff: APPROVE-WITH-NITS (P3 only). Executable
  51-case A/B matrix base-vs-patched on simulated CUDA: byte-identical.
  Blast radius: exactly 4 source files + 1 test file; sampling.py untouched.
- #3 merge readiness: KEEP-DRAFT (doc fixes applied to PR body today:
  +30/-6 stat, real H800 log-line expectation, accurate external-prerequisites
  wording). Zero code blockers; MERGEABLE; no force-push; maintainerCanModify.

## Test battery re-run (pristine sglang)

49/49 PASS (12 yue2 platform gates + 37 model capabilities); ruff check clean;
check_if_else clean.

## Status

- PR #1 remains DRAFT pending the real Omni ROCm e2e run; evidence script v2
  (manifest / GPU trace / short + full-config requests / SHA256 / verdict)
  armed via idle-watcher at /workspace/yue2-omni-pr/smoke_test_omni_yue2_rocm.sh.
- WSB full run still in progress at check time (~302/384); no interference.
- H800 execution remains NOT TESTED locally — never claimed as such.
