# Author message — for review (single post, two asks)

**To:** @yiakwy-xpu-ml-framework-team (on your preferred thread — omni PR#1
or a single issue; please don't multi-post)

Hi — the W7900 verification work for your YuE2 ports is complete and closed
(full WildSongBench 384/384 on both the SGLang and Omni ROCm paths, BS=1 +
concurrency sweep, integrity audits; evidence branch
`AIwork4me/YuE2-SGLang-ROCm@validation/gfx1100-rocm7141`). Everything below
is prepared for your acceptance — nothing has been pushed to your branches.

**Ask 1 — integrate the reviewed compatibility contributions and run the
focused H800 check.**

- Merge yiakwy…/sglang-omni#1 (`eca7770f`) and #2 (`4c089d19`) into
  `add_yue2` (disposable-worktree preview: zero conflicts, 62/62 unit
  tests, tree-identical to the PR heads — report 04).
- Cherry-pick `ae11c6ad` from
  `AIwork4me/sglang-omni@preview/omni-yue2-integration-style` (mechanical
  lint fixes; your ~166 leading-underscore names remain yours to rename).
- On the SGLang side, if you want CI unblocked: cherry-pick
  `AIwork4me/sglang@fix/yue2-upstream-lint` (`1a9f2d92`, parent
  `ced0ef7d`), then merge `main` — the single registry.py conflict
  resolution is documented to the line (report 07).
- Then one focused H800 smoke run on the integrated commit (checklist:
  report 05 — one short deterministic song, dispatch-evidence capture;
  explicitly NOT a new dataset run).

**Ask 2 — review the prepared official-PR/CI unblock materials so we can
move both upstream PRs forward.**

- Proposed maintainer-ready PR description + one-page summary for omni
  #2540 (your NVIDIA statements preserved verbatim; reports 02/02b).
- CI activation analysis: what a maintainer must approve, which labels
  exist (no YuE2 CI selector today), smallest appropriate set (report 03);
  run-ci mechanics for SGLang #42106 (report 08).
- If you'd rather receive these as PRs against `add_yue2` than branches to
  cherry-pick, say the word and we'll open exactly one per concern — no
  duplicates of #1/#2/benchmark-fork#1 will be created.

Everything is in `AIwork4me/YuE2-SGLang-ROCm`, branch
`handoff/yue2-upstream-merge-readiness`, `reports/merge_readiness/`.

One post, your call on ordering. Thank you for the review time.
