# 01 — SGLang #42106 Merge-Ready Closure (2026-10-26)

Integration branch: **`AIwork4me/sglang:integration/yue2-sglang-gfx1151-merge-ready`**
(local: `upstream/sglang-merge`, head `44c8fa51f` after review fixes below;
initial validated head `5dc9b33a8`; pushed to the fork — push verified for
`5dc9b33a8`, `44c8fa51f` push queued during a network outage window)

## 1. CI failure classification for PR #42106 (refreshed 2026-10-26)

| Check | Result | Classification |
|---|---|---|
| `call-gate / pr-gate`, `pr-gate` (many, 3–6 s) | fail | **Label gate**: job step "Require run-ci label (optional)" — maintainer-controlled; not a code failure (verified via jobs API step list) |
| `pr-test-*-finish` (3 s) | fail | Orchestrator finish jobs blocked behind the gate; **GPU tests skipped, not executed** |
| `lint` (2 m 47 s) | fail | Real lint execution on the PR head; addressed by prepared commit `1a9f2d92` and re-verified here against current main's unchanged hook pins |

No other executed-and-failed checks. GPU CI remains gated on the maintainer
`run-ci` label — outside our control, unchanged from prior analysis.

## 2. Integration construction (authorship preserved)

Base: author `add_yue2` @ `ced0ef7d` (re-verified equal to PR #42106 head).

```
ced0ef7d (author)  add concurrency test
8367a579 (author)  add YuE 2 e2e test
6bd2ad33 (author)  add YuE 2 support
60e3987e  merge --no-ff def437fb  ← ROCm reference path, fork PR #1 head
6b368483  cherry-pick 1a9f2d92    ← prepared lint commit (authorship kept)
6a875702  merge origin/main 5ef99013a (latest main at merge time)
5dc9b33a  style: canonicalize conflict-resolved files (ruff 0.15.1)
```

`def437fb` enters as a **merge** (reviewable as exactly fork PR #1); the lint
commit is a cherry-pick (author/date preserved). No author-owned branch was
modified; nothing was force-pushed.

## 3. Conflict resolutions vs latest main (`5ef99013a`)

Main moved ~18 days past the prior analysis (`aaf5f397` → `5ef99013a`) and
**flattened the `experimental/` directory** and reorganized `kernels/ops/` and
`test/` layouts, enlarging the conflict surface beyond the 2 files known on
2026-10-16.

| # | File | Root cause | Resolution | Regression risk / evidence |
|---|---|---|---|---|
| 1 | `multimodal_gen/registry.py` | author inserted yue2 entry above a fastvideo key that main renamed (`fasth3-4-step…` → `fasth3-8-step-v2`) and extended (`omni-8-step-v1`) | keep `"m-a-p/yue2-3b": "YuE2Pipeline"` + adopt main's two new fastvideo entries; drop renamed-away key | low — dict literal; `py_compile` PASS; both sides' entries present |
| 2 | `.codespellrc` | both sides appended words to `ignore-words-list` | union: main's `ser` + ours `MoT,mot` | none — codespell PASS on changed files |
| 3 | `experimental/yue2/{README,__init__,http_api}.py` → `yue2/` | main flattened `experimental/` (e.g. `experimental/sgl-router` → `sgl-router`) | accept git's directory-rename relocation to top-level `yue2/` | low — standalone client files; zero stale `experimental/yue2` references remain repo-wide (grep clean) |
| 4 | root `__init__.py` (from `experimental/__init__.py`) | rename heuristic proposed a repo-root package file | **removed** — main has no root `__init__.py`; a root package file would be wrong | none |
| 5 | `test/srt/models/test_yue2_platform_gates.py` → `test/registered/unit/models/` | main reorganized `test/` to `test/registered/unit/…` | accept relocation to main's layout | low — suite passes from new location (21/21) |
| 6 | `srt/models/yue2/song.py` (lint × guards) | lint commit reformatted the exact regions where `def437fb` inserts guards | merged: lint formatting + all guard imports; one hunk resolved manually (`deepselect_runnable` folded into consolidated import block) | guard-function ASTs verified identical to `def437fb` (see §5) |

### Kept-as-is (documented divergence, not silently resolved)

- **`kernels/ops/deep_select.py` (author-vendored) vs main's new
  `kernels/ops/attention/deep_select.py`** — the PR *added* its own DeepSelect
  wrapper (adapted from tokenspeed, NOTE(yiakwy), alignment 1024, caps
  `(9,0),(10,0),(10,3)`); upstream main independently landed a **different**
  implementation (`ops/attention/`, alignment 128, `page_transform`, no
  `get_stride_requirement`, `is_deepselect_supported()` without device arg).
  Swapping wrappers would silently change CUDA kernel-loading behavior —
  exactly what this mission must not do without NVIDIA validation. The
  integration therefore **keeps the author's vendored file** (their tested
  CUDA path, imported lazily by `yue2/fastpath.py`) and flags the duplication
  as an upstream-review decision item: author/maintainer should converge on
  one implementation, validated on NVIDIA hardware. This is the only known
  maintainability objection upstream review may raise against the preview.

## 4. Capability gates (ROCm) — verification

All four gates from `def437fb` retained and verified against the integrated
tree (function-level AST comparison vs the PR branch — identical):

1. `song.py::_generate_song_tokens_step_graph` → raises `_StepGraphUnavailable`
   when `deepselect_runnable()` is false (falls back to looped path).
2. `fastpath.py::fast_sampler_available()` → requires
   `torch.cuda.is_available()` **and** `is_deepselect_supported()`.
3. `fa3.py::_load_varlen()` → loads the shared varlen wrapper only when
   `torch.version.hip is None`; ROCm uses validated
   `torch.ops.aten._flash_attention_forward`.
4. `batched.py::batched_ar_enabled()` → delegates to `fast_sampler_available()`.

CUDA fast paths preserved: every gate keys on the capability check
(`is_deepselect_supported()` from the author's own module), never on platform
sniffing; on supported NVIDIA devices all paths behave exactly as the author
authored them (verified by the CUDA-positive fake-device tests below —
simulated dispatch evidence, not hardware evidence).

## 5. Validation results (integration head `5dc9b33a8`)

| Check | Result | Evidence |
|---|---|---|
| Conflict count | 0 unmerged after resolution | `git ls-files -u` empty |
| Delta vs main | 36 files = exactly PR surface (relocated) + platform-gates test | `git diff origin/main..HEAD --name-only` |
| Compile | all 34 changed `.py` files `py_compile` PASS | run log |
| Guard preservation | guard functions AST-identical to `def437fb` | `ast.dump` comparison (7 functions) |
| Platform-gates tests | **21/21 PASS** | `pytest test/registered/unit/models/test_yue2_platform_gates.py` (env: venv + `PYTHONPATH=<integration>/python`) |
| ruff (CI-equivalent) | PASS | pinned ruff 0.15.1, hook args `--select=F401,F821,F823,UP037` on all changed files |
| ruff format | clean after fixup commit | 31 files formatted, 0 pending |
| isort (pinned 7.0.0) | PASS | check-only clean, repo `.isort.cfg` |
| codespell (pinned 2.4.1, `.codespellrc`) | PASS | no findings |
| Stale path references | none | repo-wide grep for `experimental/yue2` empty |

Note on methodology: the bare `ruff check` default rule set (E4/E7/E9/F)
reports E402/F811 in `test_server_yue2.py`; these are **not** part of the
repo's CI surface (the pre-commit hook selects only F401,F821,F823,UP037 —
`.pre-commit-config.yaml`). Main's pre-commit drift vs `ced0ef7` is
exclusion-list-only; hook versions unchanged.

## 6. Acceptance criteria status

- Merge preview resolves all conflicts with latest main — **PASS**
- YuE2 compatibility code retained — **PASS** (AST-verified)
- No unrelated source changes — **PASS** (36-file delta = PR surface + gates test)
- Targeted pre-commit checks pass — **PASS** (pinned versions, CI args)
- Targeted tests pass — **PASS** (21/21)
- NVIDIA paths logically preserved — **PASS** in code + simulated dispatch tests; physical H800 validation remains the author's (as before)
- Unresolved issues recorded — one: DeepSelect wrapper duplication (§3, flagged for upstream review; no action possible without NVIDIA validation)

## 7. What the author can do with this branch

`git fetch https://github.com/AIwork4me/sglang.git integration/yue2-sglang-gfx1151-merge-ready`
then review the two merge commits + fixup; or cherry-pick the same sequence
(their choice of vehicle). Everything is additive on top of their `add_yue2`;
no history rewrite.

Next: Phase 2 runs a physical gfx1151 E2E generation from this exact tree
(report `02_GFX1151_SGLANG_E2E.md`).

## 8. Addendum — independent review outcome and fixes (same day)

Three independent reviews (see `reviews/REVIEW_{A,B,C}_*.md`):

- Review A (ROCm correctness): **PASS-WITH-P2s** (0 P0/P1). Gates verified
  live on gfx1151; aten fallback matched an fp32 SDPA reference (max err
  0.0048).
- Review B (NVIDIA preservation): **PASS-WITH-P2s** (0 P0/P1). Fast-path
  bodies AST-identical to the author's code; env-var truth tables identical
  on supported CUDA devices.
- Review C (maintainer simulation): **FAIL — 2 P0 / 2 P1** → all four fixed
  in commit `44c8fa51f` after independent verification of each finding:
  - P0-1 vendored `ops/deep_select.py` violated main's kernels-namespace
    invariant (`test_kernels_namespace.py:278`; rule previously enforced on
    this exact kernel in #41349) → relocated (git mv) to model-private
    `srt/models/yue2/_deep_select.py`.
  - P0-2 gate test lacked `register_cpu_ci` + `__main__`, breaking
    `run_suite.py` collection → registration added (mirrors
    `test_deepseek_mla_dispatch.py`).
  - P1-1 route loader was a repo-root filesystem path with silent skip →
    router packaged as `entrypoints/yue2_api.py` with a direct import.
  - P1-2 DeepSelect duplication resolved by the model-private placement.
  - Plus Review-A P2-A hardening: pip-fallback `deepselect_runnable()` now
    requires `torch.version.hip is None`.

Post-fix validation: **121/121** (gates suite incl. updated pip-fallback
test + full kernels-namespace suite), lint clean on touched files, and a
fresh server boot + tiny `/v1/audio/generations` request **HTTP 200 in
5.9 s** on gfx1151 from the fixed tree (valid 0.8 s WAV). Remaining P2/P3
items are recorded in the review files as follow-ups for the author
(notably: hasattr-checks for fused ops (P2-B), physical H800 validation
(P2-B review B), ruff `files:` regex coverage of top-level docs (P2-1
review C)).
