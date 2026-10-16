# SGLANG_PR1_HANDOFF.md — 2026-10-14 session

Mission: YuE2 dual-platform (ROCm W7900 + NVIDIA H800 handoff) minimal
compatibility contributions to both author-owned feature branches.
MERGE FIRST / SAME-CODE CROSS-VENDOR ACCEPTANCE.

## 1. Contributions (both delivered; GitHub-verified)

### 1a. SGLang cross-fork PR (NEW this session)

- URL: https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork/pull/1
- Title: `fix(yue2): enable ROCm fallback while preserving CUDA fast paths`
- Base: `yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork:add_yue2`
  @ `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` (verified unchanged)
- Head: `AIwork4me:fix/yue2-rocm-reference`
  @ `def437fb7949f26bd1b06473882fd928757c6377` (parent = ced0ef7d EXACTLY;
  created via Git Data API — egress proxy blocks git smart-HTTP)
- PR delta: 1 commit, 5 files, +456/−9, mergeable=true
  (`unstable` = fork CI `action_required`, no failing checks)
- Local validated equivalent: `32d6a96` on
  `/workspace/yue2-sglang-rocm-w7900/upstream/sglang:fix/yue2-rocm-reference`
  (pristine base `27ee2a2` = ced0ef7 tree; remote diff verified byte-equal
  to local diff, per Auditor B and this session's compare check)
- Files:
  - `python/sglang/srt/models/yue2/fastpath.py` (+20/−4): new
    `deepselect_runnable()` capability probe (in-tree
    `is_deepselect_supported()`; pip backend without probe keeps the
    original `torch.cuda.is_available()` check; detection errors fail
    safe); `fast_sampler_available()` delegates.
  - `python/sglang/srt/models/yue2/song.py` (+7/−1): step graph raises the
    existing `_StepGraphUnavailable` when the kernel cannot run, BEFORE
    graph/GraphSampler construction → looped reference path.
  - `python/sglang/srt/models/yue2/fa3.py` (+6/−2): HIP skips the shared FA
    op (imports OK but CUDA-only kernels fail at call time — verified
    `ModuleNotFoundError: flash_attn` on gfx1100); native ATen varlen
    (seqused_k/GQA preserved) is the validated route; CUDA dispatch
    unchanged.
  - `python/sglang/srt/models/yue2/batched.py` (+7/−2):
    `batched_ar_enabled()` requires the capability so CUDA-only
    `BatchedGraphSampler` pooled sessions are never constructed on
    unsupported devices. PyTorch CUDA GraphAR pooling stays enabled on HIP.
  - `test/srt/models/test_yue2_platform_gates.py` (+416): 21 dispatch tests.
- NOT included (intentionally): quark/aiter + mem_cache/sgl_kernel import
  guards — shared-infrastructure prerequisites, see §4.

### 1b. SGLang-Omni PR (EXISTING; updated this session)

- URL: https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1
- Base: author `add_yue2` @ `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` (unchanged)
- Head: `AIwork4me:fix/yue2-rocm-reference`
  @ `eca7770fe196fe970f7d847858a5f92444b75538`
  (2 commits: `50c91c08` original + `eca7770f` review update; parent chain
  intact; local content-equivalent commit `91dccda1`)
- PR delta total: 5 files (+237/−6 core, then comment-only +11/−10),
  mergeable=true
- MAINTAINER ENGAGED (2026-10-14 05:04–05:14Z): 3 review comments + final
  "LGM after updating the comments". Addressed in `eca7770f`:
  - song.py: applied suggested `# note (rocm): add fast TopK support`
    verbatim; all AI-notation scrubbed (repo policy)
  - fastpath.py: note now points at maintainer's
    flash-float-jit-kernels as future ROCm top-k (capability probe
    auto-enables when runnable)
  - fa3.py: docstring notes ROCm flash-attn-2 build can later replace ATen
    via the shared path (same seqused_k/GQA contract); ATen remains the
    zero-dependency validated route — answered in reply comment
  - 12/12 platform-gate tests re-run PASS after the update
- No duplicate PRs (verified: exactly one PR targets add_yue2 from
  AIwork4me in each fork).

## 2. Real W7900 runtime evidence — SGLang minimal branch, no fallback flags

Host: AMD Radeon PRO W7900D (gfx1100), torch 2.12.0+rocm7.14.1
(`torch.version.cuda=None`, capability (11,0)). Real `sglang serve`
(127.0.0.1:31001), tree = ced0ef7 + 5-file patch + disclosed overlay
(runtime tree `c2487d8`; its 4 yue2 runtime sources byte-identical to
`32d6a96` — Auditor A). Server log proves ONLY `SGLANG_YUE2_VAE_DIR` was
exported — `SGLANG_YUE2_FAST_SAMPLER / STEP_GRAPH / FA3 / BATCHED_AR` were
NOT set (mission crucial test): the platform gates selected every path.

| request | HTTP | wall | artifact | dispatch (plan.json, both AR phases) |
|---|---|---|---|---|
| smoke (semantic 300 / abc 256 / ode 4 / vae 192) | 200 | 35.7 s | 12.00 s stereo 48 kHz WAV, 2,303,788 B, RMS 2225.7, finite, non-silent, sha256 `d99ae6b00e5c1d6fd77c9ea46f92652daa53fd4bfc1af76df57776b8f676e06d` | `sampler=reference`, `execution=cuda_graph`, `attention=flash` (ATen route) |
| realistic (WSB budgets: semantic 9000 / abc 4096 / ode 32 / vae 1024) | 200 | 338.3 s | 114.96 s stereo 48 kHz WAV, 22,072,108 B, RMS 4820.3, sha256 `570e4aa9f87e32f43b6a95798db7a6ac7a9309f2bdadfd938ac24d883bcd527f` | abc 1168 tok / semantic 2875 tok, `truncated=false`, same dispatch |

Model loading, real ROCm attention (ATen varlen), loop/reference AR, NAR,
VAE and complete song generation exercised; zero ERROR/Traceback lines in
the server log. Raw results: `validation_minimal_branch/*.json`; log
excerpt: `server_minimal_log_excerpt.txt`. Unit matrix on the same host:
21/21 PASS (`test_yue2_platform_gates.py`, re-run independently by
Auditor A). Omni branch: 12/12 PASS (comment-only update re-run).

Note: `peak_memory_mb` in the response JSON reports 0.0 (server-side
telemetry field not populated in this build); VRAM occupancy was not
re-telemetered this session. The 384-candidate WSB run retains the full
GPU telemetry record (peak_vram_bytes in generation_summary.json).

## 3. CUDA preservation (unit-proven; physical H800 pending)

21-case matrix includes: simulated CUDA (probe True) fast-sampler ON,
step-graph ENTERED (GraphSampler constructed once), shared FA op called
with `seqused_k/causal=False/ver=3` verbatim, batched AR ON; pip-backend
without probe = original check; all four env overrides win on CUDA;
`FAST_SAMPLER=0` does not disable batched AR on runnable hardware;
unsupported capability / missing backend / raising probe / HIP sim →
reference paths with `BatchedGraphSampler` construction count 0.
Pre-existing ruff findings in author code verified identical on pristine
ced0ef7 (duplicate imports song.py:17/23; unused dtype) — untouched.
P2 disclosures in PR body: unsupported-NVIDIA SMs (8.x/12.0) now get the
fail-safe reference path instead of pristine's crash-at-decode;
`SGLANG_YUE2_SESSION=0` (`use_fast_sampler=True`) bypass remains
pre-existing upstream behavior.

## 4. External dependency requirements (disclosed overlay, NOT in PRs)

Pristine ced0ef7 fails to import on gfx1100 in shared infrastructure
(tracebacks in log excerpt / probe script output):
- `ModuleNotFoundError: aiter` — quark W4A4-MXFP4 schemes import aiter
  unconditionally under `_is_hip` (quark_w4a4_mxfp4.py:86 and chain)
- `ModuleNotFoundError: sgl_kernel` — mem_cache/memory_pool_host.py:27
  (`sgl_kernel.kvcacheio` on HIP)
Validation applied the previously-published 6-file import-guard overlay
(`validation_minimal_branch/external-import-guards.patch` = evidence-repo
patches 0001-0003 subset + 0008) in an isolated worktree
(`validation/w7900-overlay` @ `a5e0be0`), never in the PR branches. These
are separate shared-infrastructure prerequisites for any ROCm serving of
this tree. YuE2 package itself imports clean on pristine.

## 5. Historical evidence reuse (Phase 5 disclosure — NOT a fresh test)

The completed WildSongBench FULL audit (run `wsbfull20261012T0041Z`,
2026-10-12→13, this host) is SUPPORTING REPRODUCIBILITY EVIDENCE only:
it used the author head (ced0ef7) plus the older broad local patches
(0001-0009) WITH explicit fallback flags (`SGLANG_YUE2_FAST_SAMPLER=0`,
`STEP_GRAPH=0`, `FA3=0`, `BATCHED_AR=0`, ...) — a different, older patch
set, not the minimal branch validated today. Final state: 384/384
verified, verdict FULL, generation_summary wall 21,369 s. Official scoring
disclosures (unchanged from `YUE2_FINAL_MERGE_AND_WSB_HANDOFF.md`):
evaluator Qwen3-ASR (different-family ASR; capped-ASR samples; PER
selection methodology over 2 candidates/prompt × 192 prompts), exact model
and evaluator revisions recorded there; no NVIDIA/AMD quality-parity claim
is made. WSB artifacts untouched this session (manifest mtime
2026-10-13T14:53Z; Auditor A re-verified).

## 6. Review + audit verdicts (all recorded)

| Role | Scope | Verdict |
|---|---|---|
| Independent code review (pre-submit) | 10 checklist areas, adversarial | APPROVE — P0:0, P1:0, P2:4 (all documented in PR body) |
| Auditor A — ROCm runtime & evidence integrity | 7 claims re-executed from primary artifacts | **PASS** |
| Auditor B — NVIDIA regression & minimality | 7 items, 16-combo boolean equivalence | **PASS** |
| Auditor C — GitHub targeting & merge readiness | both PRs, parentage, no-dup, no-main-PR | **PASS** (found maintainer engagement on Omni PR — handled) |

## 7. H800 validation checklist (author action; SAME patched commits)

SGLang branch (`def437fb`):
1. `python -m pytest test/srt/models/test_yue2_platform_gates.py -v` → expect 21 PASS
2. `sglang serve --model-path YuE2-3B --warmup-mode off` with NO
   SGLANG_YUE2_* flags; POST /v1/audio/generations smoke
3. Expected dispatch on SM 9.0: `sampler=deepselect*`, step-graph /
   batched-AR eligible, shared FA op active
Omni branch (`eca7770f`): same procedure (12-test file; expected dispatch
mirrors the platform gates; see PR #1 instructions).

Code-level equivalence ≠ physical test: dual-vendor runtime PASS requires
the author's real H800 execution.

## 8. Maintainer actions to merge

- SGLang PR #1 (benchmark fork): approve-and-run the 3 `action_required`
  workflows (or accept no-runner), then Merge / cherry-pick `def437fb`
  into add_yue2. Merging stages the fix into upstream sgl-project/sglang#42106
  (head branch), which sgl-project maintainers merge separately.
- Omni PR #1: maintainer already "LGM after updating the comments";
  requested updates pushed (`eca7770f`) + reply posted → re-approve and
  Merge. Related official: sgl-project/sglang-omni#2540.

## 9. Final states (kept separate; as of session end 2026-10-14 ~05:30Z)

| State | Value |
|---|---|
| SGLANG_ROCM_W7900_VERIFIED | TRUE (this session; no-flag run, §2) |
| SGLANG_CUDA_H800_VERIFIED | FALSE — pending author H800 run (§7) |
| OMNI_ROCM_W7900_VERIFIED | TRUE (2026-10-13 evidence; comment-only delta since) |
| OMNI_CUDA_H800_VERIFIED | FALSE — pending author H800 run |
| AUTHOR_SGLANG_BRANCH_INTEGRATED | FALSE — PR open, awaiting maintainer |
| AUTHOR_OMNI_BRANCH_INTEGRATED | FALSE — conditional LGM, awaiting re-approve+merge |
| OFFICIAL_SGLANG_MERGED | FALSE — sgl-project/sglang#42106 open |
| OFFICIAL_OMNI_MERGED | FALSE — sgl-project/sglang-omni#2540 open |
