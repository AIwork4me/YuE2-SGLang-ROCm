# 07 — Upstream Comment Drafts (merge-readiness mission, 2026-10-26)

Status: **DRAFTS — not posted.** Posting requires owner approval (standing
policy since the benchmark mission). Each draft is copy-paste ready.

## 1. sglang#42106 — comment for the PR author (yiakwy team)

> Hi — an AMD-side follow-up to our earlier compatibility PRs, with
> everything assembled into one merge-ready branch so nothing here needs
> re-derivation:
>
> **`AIwork4me/sglang @ integration/yue2-sglang-gfx1151-merge-ready`**
> (`44c8fa51f`) = your `add_yue2` (`ced0ef7d`) + our ROCm guards
> (`def437fb`, entered as a merge) + the pre-commit lint pass (`1a9f2d92`,
> cherry-picked with your original authorship) + a merge of current
> `main` (`5ef99013a` at build time) with all conflicts resolved + three
> small fixes from an independent maintainer-style review.
>
> What the main-merge resolution handles for you: `registry.py` (keeps your
> yue2 entry, adopts main's renamed fastvideo keys), `.codespellrc` (union),
> the `experimental/` flattening (your standalone files at top-level
> `yue2/`, and the `/v1/audio/generations` router packaged as
> `multimodal_gen/runtime/entrypoints/yue2_api.py` so it survives wheel
> installs), and your vendored DeepSelect wrapper relocated verbatim to
> `srt/models/yue2/_deep_select.py` — main now enforces
> `kernels/ops/*.py == {__init__.py}` (it was applied to this kernel in
> #41349) and `test_kernels_namespace.py` fails otherwise.
>
> Validated on Radeon 8060S (gfx1151/ROCm): 121/121 in
> `test_yue2_platform_gates.py` + the kernels-namespace suite, and a real
> `sglang serve --model-type diffusion` → `POST /v1/audio/generations` run
> producing 47 s and 112 s 48 kHz stereo WAVs with **no
> `SGLANG_YUE2_*` overrides set** — the capability gates select the
> reference paths on their own. NVIDIA semantics are untouched: independent
> review verified the fast-path function ASTs identical to your code and
> identical env-var truth tables on supported devices; simulated dispatch
> tests only, no H800 hardware claims.
>
> If you'd rather assemble it yourself, the exact sequence and conflict
> notes are in the evidence repo
> (`AIwork4me/YuE2-SGLang-ROCm`, `reports/merge_readiness/01_…`). Happy to
> adjust anything — and separately, the `run-ci` label is the only thing
> between this PR and its GPU checks.

## 2. sglang-omni#2540 — comment for the PR author

> Quick refresh from the AMD side: the four-step integration we handed over
> earlier (ROCm PR #1 `eca7770f` + long-lyrics PR #2 `4c089d19` + style
> commits `ae11c6ad`/`b91b9544`) was re-verified today on your unchanged
> `85ae4b73` — still zero conflicts, still the exact tested tree
> (`363073e6`), and now also green on a second AMD device (Radeon 8060S:
> 39/39 focused tests including the prompt-164 long-lyrics regressions;
> omni's pinned lint green).
>
> Since `main` moved ~380 commits past your merge base, we also prepared
> **`AIwork4me/sglang-omni @ integration/yue2-omni-merge-ready`**: your
> branch + the four steps + current main resolved (exactly one overlapping
> file, `tests/unit_test/models/test_model_capabilities.py`). Grab it whole
> or cherry-pick the resolution — report 03 in the evidence repo has the
> construction details and test matrix.

## 3. Author-fork PR comments (compatibility PRs)

### 3a. yiakwy…/AMD-sglang-benchmark-fork#1 (SGLang ROCm)

> Re-verified against current `main` today: this PR's guards are now also
> validated inside the full integration preview
> (`AIwork4me/sglang:integration/yue2-sglang-gfx1151-merge-ready`, see the
> #42106 comment) — same five files, unchanged, 121/121 dispatch/namespace
> tests, real gfx1151 generation with no env overrides. Still independent
> of the lint fix; still yours to merge or cherry-pick as-is.

### 3b. yiakwy…/sglang-omni#1 (Omni ROCm) and #2 (long lyrics)

> Both re-verified today on the unchanged `85ae4b73` base (bit-exact
> integration rehearsal, 39/39 tests on a second AMD GPU incl. the
> prompt-164 regressions from #2). They remain the two first steps of the
> documented integration sequence; the new
> `integration/yue2-omni-merge-ready` branch is built on top of exactly
> these commits — merging them here stays the cleanest route.

## 4. sglang-omni#2875 — close comment (posted by owner when closing)

> Closing this in favor of the narrower review surfaces — my apologies for
> the noise.
>
> This branch was cut from the author's `add_yue2`, so the PR diff shows the
> full YuE2 implementation, but its actual content is just the long-lyrics
> input-cap fix. That fix is already open for review as
> yiakwy-xpu-ml-framework-team/sglang-omni#2 (same commits
> `4ad6658b`/`4c089d19`), targeting the author's `add_yue2` branch where the
> YuE2 integration is being staged for #2540. The YuE2 implementation itself
> belongs to #2540 and should land through the author's branch, not a
> third-party PR.
>
> Maintainers: nothing here needs merging separately — #2 carries the fix.

## 5. Optional: independent `main` PR (host-boot import guards)

> **Title:** [Fix] Guard HIP-side `sgl_kernel`/`aiter` imports for non-CDNA
> ROCm hosts
>
> Current `main` fails at `import sglang` on HIP hosts without CUDA wheels:
> `fused_moe.py` imports `sgl_kernel` unconditionally under `elif _is_hip:`,
> and three quark scheme files import `aiter` the same way (aiter ships only
> for gfx94x/95x). On e.g. gfx1151 (Radeon 8060S) with torch
> rocm wheels + `--no-deps` installs, every server start dies before model
> load. Four-file patch attached — try/except with call-time failure, no
> behavior change where the wheels exist. Validated end-to-end on gfx1151
> (YuE2 E2E generation on top of these guards).
