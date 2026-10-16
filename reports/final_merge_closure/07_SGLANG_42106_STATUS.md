# 07 — SGLang #42106 status (re-verified 2026-10-16)

## Branch integrity (verified via GitHub API)

- `AIwork4me/sglang@fix/yue2-upstream-lint` head
  `1a9f2d92a201b21242ca6c1bbe8a070189b0a913`, parent exactly
  `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` (PR #42106 head, unchanged),
  29 files — matches report 06 of `merge_readiness`.
- No new branch or PR created in this mission (no change was necessary).

## Lint reproduction (this mission, pinned toolchain)

Fresh clone of the branch; `pre-commit run --files <29 files>` with the PR's
own pinned config (pre-commit-hooks v6.0.0, isort 7.0.0, ruff v0.15.1,
codespell v2.4.1): **all six previously-failing hooks PASS** —
trailing-whitespace, end-of-file-fixer, isort, ruff, ruff format, codespell.
Zero file modifications, clean tree.

## Safety re-checks

- Live module key intact: `yue2_pipeline.py` still has `"mot": runtime.model`
  (line 45) and both `get_module("mot")` lookups — the codespell trap
  correctly avoided.
- `.codespellrc` ignore list carries the appended `MoT,mot` (plus the two
  real comment-typo fixes).

## Conflict re-check vs CURRENT upstream main (`aaf5f397a5…`, 857 commits
ahead of merge base `ba683062` — upstream moved 18 commits since the last
analysis; overlap surface UNCHANGED)

- Of the PR's 35 files, exactly 2 touched on main since the merge base:
  `multimodal_gen/registry.py` (4 commits) and
  `multimodal_gen/runtime/entrypoints/http_server.py` (2 commits).
- 3-way merge: registry.py → exactly 1 conflict hunk (same shape as before:
  author inserts `"m-a-p/yue2-3b": "YuE2Pipeline",` above the fastvideo
  entry that main renamed to `fastvideo-fasth3-8-step-v2`); http_server.py →
  **auto-merges cleanly, parses OK**.
- The prepared both-sides resolution stands (patches/
  sglang_registry_conflict_resolved.py = current main + the one yue2 line).

## Author actions (unchanged)

1. `git fetch https://github.com/AIwork4me/sglang.git fix/yue2-upstream-lint
   && git cherry-pick FETCH_HEAD` → lint green.
2. `git merge upstream/main`, resolve registry.py keeping BOTH
   `"m-a-p/yue2-3b": "YuE2Pipeline",` and
   `"fastvideo/fastvideo-fasth3-8-step-v2": "FastH3Pipeline",`.
3. Ask a maintainer for the `run-ci` label (or /tag-run-ci-label) — the
   finish-gate jobs fail only on the missing label.

## Statuses

- ROCm compatibility PR (benchmark-fork#1, head `def437fb`): still open,
  still independently reviewable; do not bundle with the lint fix.
- Our closed private evidence PRs #1/#2: no action required.
