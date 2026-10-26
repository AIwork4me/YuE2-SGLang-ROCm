# 11 — Final Consolidated Upstream Comments (2026-10-27)

Three comments total (per final-review directive): one author-facing comment
per official PR + one close-and-redirect for Omni #2875. Ready to paste;
**nothing posted without owner approval**.

---

## Comment 1 — sglang#42106 (to the PR author)

> Hi — AMD-side wrap-up with everything assembled and re-validated against
> current `main` as of 2026-10-27, so nothing needs re-derivation on your side.
>
> **Main deliverable — merge-ready branch:**
> [`AIwork4me/sglang@integration/yue2-sglang-gfx1151-merge-ready`](https://github.com/AIwork4me/sglang/tree/integration/yue2-sglang-gfx1151-merge-ready)
> (`44c8fa51f`) = your `add_yue2` (`ced0ef7d`, untouched) + the ROCm guards
> (`def437fb`, entered as a true merge) + the pre-commit lint pass
> (`1a9f2d92`, cherry-picked with your authorship) + current `main`
> (`5ef99013a` at build) fully conflict-resolved + three small fixes from an
> independent maintainer-style review.
>
> **Freshness check (2026-10-27):** main advanced another 31 commits to
> `01759f0a6`; we merged it on a review branch
> ([`review/yue2-sglang-main-delta-20261027`](https://github.com/AIwork4me/sglang/tree/review/yue2-sglang-main-delta-20261027))
> — zero file overlap, zero conflicts, **122/122 tests** and a live
> `sglang serve` + `/v1/audio/generations` HTTP 200 smoke. So the branch is
> still current as of today.
>
> **Exactly what was tested, on Radeon 8060S (gfx1151, ROCm):**
> - `44c8fa51f`: 121/121 unit tests (dispatch gates + kernels-namespace
>   suite), CI-equivalent lint green, real server boot + seeded generation
>   (HTTP 200).
> - `bcb496ab9` (same branch, pre-review-fix): full E2E lengths — 47.0 s and
>   112.1 s valid 48 kHz stereo WAVs, finite, non-silent, with **no
>   `SGLANG_YUE2_*` env overrides** — the capability gates select reference
>   paths on unsupported devices themselves.
> - Honest scope: CUDA fast-path preservation is verified by code identity
>   (guard functions AST-identical to your originals; env-var truth tables
>   unchanged on supported devices) and simulated dispatch tests only —
>   no H800 hardware claims.
>
> **What the main-merge handles for you:** registry conflict (keeps your
> yue2 entry, adopts main's renamed fastvideo keys), `.codespellrc` union,
> `experimental/` flattening (your standalone files → top-level `yue2/`,
> router packaged as `entrypoints/yue2_api.py` so wheel installs work), your
> vendored DeepSelect wrapper relocated verbatim (git mv) to
> `srt/models/yue2/_deep_select.py` — main now enforces
> `kernels/ops/*.py == {__init__.py}` and `test_kernels_namespace.py` fails
> otherwise — and CI registration for the gate test.
>
> **Ask:** (1) merge the branch into `add_yue2` (one `git merge --no-ff
> FETCH_HEAD`) or replay its steps — either is fine by us; (2) request the
> `run-ci` label from a maintainer (it is the only red check left besides
> lint, which this branch fixes); (3) one H800 smoke of the integrated head
> per the checklist we handed off earlier. Full evidence:
> [`AIwork4me/YuE2-SGLang-ROCm` → `reports/merge_readiness/`](https://github.com/AIwork4me/YuE2-SGLang-ROCm/tree/handoff/yue2-merge-readiness-20261026/reports/merge_readiness).
>
> Separately (independent of this PR, feel free to ignore here): current
> `main` cannot `import sglang` on HIP hosts without CUDA wheels — four-file
> fix with tests at
> [`fix/hip-host-import-guards`](https://github.com/AIwork4me/sglang/tree/fix/hip-host-import-guards).

---

## Comment 2 — sglang-omni#2540 (to the PR author)

> Hi — final AMD-side status for this PR, re-verified end to end on
> 2026-10-27.
>
> **Main deliverable — merge-ready branch:**
> [`AIwork4me/sglang-omni@integration/yue2-omni-merge-ready`](https://github.com/AIwork4me/sglang-omni/tree/integration/yue2-omni-merge-ready)
> (`3063cdf5`) = your `add_yue2` (`85ae4b73`) + the four prepared steps
> (ROCm PR #1 `eca7770f` as a merge, long-lyrics PR #2 `4c089d19` as a
> merge, style commits `ae11c6ad`/`b91b9544` as cherry-picks) — reproducing
> the recorded integration tree `363073e6` **bit-exactly** — plus current
> `main` (`b6299238` at build, 381 commits) merged with zero conflicts.
>
> **Freshness check (2026-10-27):** main advanced 9 more commits to
> `36341fc1`; merged on
> [`review/yue2-omni-main-delta-20261027`](https://github.com/AIwork4me/sglang-omni/tree/review/yue2-omni-main-delta-20261027)
> — zero overlap, zero conflicts, **60/60 tests**.
>
> **Exactly what was tested, on Radeon 8060S (gfx1151):** 39/39 focused
> tests on the rehearsal tree and 60/60 on the merged tree (dispatch gates,
> naming-policy regression, long-lyrics speech-cap including the
> WildSongBench prompt-164 pair, model-capabilities with the YuE2 entry);
> omni's own pinned lint green; and a real `sgl-omni serve` →
> `POST /v1/audio/speech` run at `3063cdf5`: HTTP 200, 79.96 s valid 48 kHz
> stereo WAV, batch=1, log line `YuE2 synth done … duration=79.96s`.
> CUDA-path preservation: simulated dispatch tests only, H800 remains
> yours.
>
> **Ask:** run the four-step sequence on `add_yue2` (exact one-liners in
> our handoff doc) and then, optionally, merge the integration branch to
> pick up the `main` resolution in one step; after that the PR needs only
> maintainer CI approval and one H800 smoke.
>
> Housekeeping on our side: we'll be closing our stray #2875 (see that PR)
> so the long-lyrics fix has exactly one review surface — your fork's PR #2.

---

## Comment 3 — sglang-omni#2875 (close-and-redirect; post together with closing)

> Closing — the long-lyrics fix here is already in review in the right
> place: yiakwy-xpu-ml-framework-team/sglang-omni#2 carries the identical
> commits (`4ad6658b`/`4c089d19`) against the author's `add_yue2`, where the
> YuE2 integration for #2540 is staged. The rest of this PR's diff is the
> author's `add_yue2` history, which belongs to #2540. Maintainers: nothing
> here needs separate merging — #2 carries the fix. (Detailed analysis:
> [`AIwork4me/YuE2-SGLang-ROCm` report 09](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/handoff/yue2-merge-readiness-20261026/reports/merge_readiness/09_UPSTREAM_PR2875_DISPOSITION.md).)
