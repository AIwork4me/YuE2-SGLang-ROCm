# 10 — Final Pre-Upstream Review Audit (2026-10-27)

Scope per directive: latest-main delta audit, ROCm host-boot closure, HTTP
security/compatibility review, evidence-accuracy corrections, consolidated
upstream communication. No development restart, no WildSongBench rerun, no
history rewrite; previously published SHAs remain immutable.

## 1. Latest-main delta audit — PASS

Refreshed SHAs (via API, then pack fetch):

| Repo | Mission snapshot | Actual at audit | Δ vs our base |
|---|---|---|---|
| sgl-project/sglang | `d41fbdc64` | **`01759f0a6`** (one commit past snapshot) | 31 commits past `5ef99013a` |
| sgl-project/sglang-omni | `878784862` | **`36341fc1`** (moved past snapshot) | 9 commits past `b6299238` |

Overlap analysis (plumbing diff-tree, no-renames):

- **SGLang**: 1 342 files changed on main; our integration surface = 35
  paths; **overlap = 0**. New main reorganizes `kernels/ops/*` further
  (Beam-model support) — none touch our surface (notably we had already
  moved the vendored DeepSelect out of `kernels/ops/`, which is why the
  ongoing reorg cannot collide).
- **Omni**: 59 files changed (MiniCPM-o / VoiceChat / Qwen3-TTS / NPU);
  our 31-file surface; **overlap = 0**.

Conflict resolution required: **none**. Review branches (existing published
branches untouched):

- [`review/yue2-sglang-main-delta-20261027`](https://github.com/AIwork4me/sglang/tree/review/yue2-sglang-main-delta-20261027)
  = `44c8fa51f` + `01759f0a6`, clean merge. Tests: **122/122**
  (gates + full kernels-namespace suite; +1 test main added). Import chain
  OK (quantization chain with overlay; packaged `yue2_api`; `http_server`).
  Live proof: server boot (Yue2Pipeline) + seeded
  `/v1/audio/generations` **HTTP 200 in 5.8 s** on gfx1151.
- [`review/yue2-omni-main-delta-20261027`](https://github.com/AIwork4me/sglang-omni/tree/review/yue2-omni-main-delta-20261027)
  = `3063cdf5` + `36341fc1`, clean merge. Tests: **60/60**.

Note: the ROCm host-boot overlay re-applies cleanly on top of `01759f0a6`
(main's only relevant change to `fused_moe.py` is in
`_fused_moe_kernel_sequence`, far from the HIP import block).

## 2. ROCm host-boot closure — PASS

All four verification properties, on vanilla main `01759f0a6`, this host
(gfx1151, no CUDA wheels):

| Property | Evidence |
|---|---|
| Without overlay: import fails | `python -c "import sglang.srt.layers.quantization"` → `ModuleNotFoundError: No module named 'sgl_kernel'` |
| With overlay: import succeeds; ops bound to `None` | same command OK; `fused_moe.gelu_and_mul is None` |
| With dependencies present: guard is a no-op | injected fake `sgl_kernel` module → try-branch binds the provided functions exactly (asserted, incl. identity check) |
| Missing ops fail explicitly, never silently | committed test asserts calling `silu_and_mul` raises `TypeError` |

Independent upstream PR candidate (not merged into any YuE2 branch):

- Branch: [`AIwork4me/sglang@fix/hip-host-import-guards`](https://github.com/AIwork4me/sglang/tree/fix/hip-host-import-guards)
  (`d05e6d989`, based on current main `01759f0a6`; 4 code files + test).
- Test: `test/registered/unit/layers/quantization/test_hip_import_guards.py`
  (3 tests, platform-independent simulation via `is_hip` patch +
  `sys.modules` blocking; CPU-CI registered; **3/3 pass** on this host).
- Reproduction instructions in the commit message and below.

Repro (before/after on any HIP host without CUDA wheels):

```bash
python -c "import sglang.srt.layers.quantization"   # before: ModuleNotFoundError
# apply branch; after: import OK; unusable ops raise TypeError at call time
```

## 3. HTTP security & compatibility review — PASS with two documented findings

### Finding S-1 (informational, upstream-precedented): unbounded speech input for YuE2

`Yue2PipelineConfig.max_speech_input_chars = None`
(`sglang_omni/models/yue2/config.py:40`) removes the generic 4 096-char
cap. Facts established by direct test on the merged tree:

- limit=None accepted a **1 048 575-char input** (TEST-1) — the residual
  resource-consumption surface is real: the only app-level body cap is
  `VoiceUploadBodyLimitMiddleware`, scoped to voice uploads only, not to
  speech JSON.
- generic models keep the cap: 4 097 chars rejected under limit=4096
  (TEST-2) — other TTS models unaffected (regression tests also green).
- prompt-164-sized (4 114 chars) input is accepted under a proposed finite
  bound of 131 072 (TEST-3).

Assessment: `None` is the **established upstream pattern** — main's own
`moss_tts`/`moss_tts_local` configs set the same `None` — so this is not a
YuE2-specific deviation; deployment-level body limits (proxy/ingress) are
the standard mitigation. Recommended follow-up for the author (not a
blocker): a finite model-specific bound (e.g. 131 072 chars, 32×
prompt-164) to bound tokenization memory while preserving every valid
full-song request.

### Finding S-2 (informational, codebase-wide): client-controlled server-side output paths

`yue2_api.py` passes client `output_path` / `output_file_name` /
`artifacts_dir` into the shared multimodal write pipeline (demonstrated
concretely: our own E2E requests directed server-side WAV writes to
arbitrary directories). This follows main's own pattern —
`video_api.py:292` passes `request.output_path` identically — so it is a
**codebase-wide hardening item** (suggested: jail to a server-configured
root, sanitize filenames), not a YuE2 regression. The author's README
explicitly scopes the route as experimental/direct-curl.

### Compatibility preserved

Prompt-164 regression tests green on rehearsal, merged, and review trees;
speech-stream/PCM constraints unchanged; no endpoint contract changes in
either delta.

## 4. Evidence accuracy — corrected

1. **Repo visibility**: `AIwork4me/YuE2-SGLang-ROCm` is **public**
   (`private: false`, verified via API 2026-10-27). Earlier working
   assumption of a private repo was wrong; all previously shared links are
   already public.
2. **Secrets scan** (public-repo gate): tracked files at HEAD scanned for
   token/key/password patterns (`ghp_/gho_/github_pat_/AKIA/private
   keys/xox/sk-/hf_/password=`) — **clean**; history filename scan for
   `.env/*.pem/*.key/secret/credential` — **clean**. Public links are safe.
3. **Tested-SHA attribution** (now explicit in report 02):
   47 s / 112 s full E2E runs → `bcb496ab9` (with host-boot overlay);
   post-review-fix re-smoke (0.8 s, HTTP 200 in 5.9 s) → `44c8fa51f`;
   today's micro-smoke (HTTP 200 in 5.8 s) → review branch on `01759f0a6`.
   The overlay is disclosed in reports 01/02/08 and §2 above.
4. **Push statuses** updated: `44c8fa51f`, `3063cdf5`, evidence branch,
   both review branches, and the overlay PR branch are all pushed and
   remote-verified (stale "queued during outage" wording removed).
5. **Changed-file counts** stated precisely: SGLang integration delta = 36
   paths with rename detection / 35 without (the `http_api.py` →
   `yue2_api.py` move counts once or twice by method); Omni = 31 either way.
6. Consolidated communication: report `11_FINAL_UPSTREAM_COMMENTS.md`
   replaces the six earlier drafts with two author comments + one
   close-and-redirect comment.

## 5. Consolidated upstream communication — READY (not posted)

See `11_FINAL_UPSTREAM_COMMENTS.md`. Posting, opening the overlay PR, and
closing #2875 all remain gated on owner approval.

## 6. Verdict summary

| Task | Verdict |
|---|---|
| 1 — latest-main delta audit | **PASS** (0 conflicts; 122/122 + 60/60 + live smokes) |
| 2 — ROCm host-boot closure | **PASS** (4/4 properties proven; PR candidate `d05e6d989` pushed) |
| 3 — HTTP security & compatibility | **PASS** (2 informational findings, precedented; prompt-164 preserved) |
| 4 — evidence accuracy | **PASS** (corrections applied; repo public + secret-free) |
| 5 — final communication package | **READY** (posting owner-gated) |

Remaining external dependencies (unchanged): maintainer `run-ci` label,
author integration, official CI, H800 physical validation.
