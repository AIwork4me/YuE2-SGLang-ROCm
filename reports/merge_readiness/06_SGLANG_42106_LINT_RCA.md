# 06 — SGLang #42106 lint RCA (reproduced, root-caused, minimal reviewed fix)

## 1. Original failure (authoritative)

CI Lint run https://github.com/sgl-project/sglang/actions/runs/37188915379
(job `lint`, step "Run pre-commit checks", 2026-10-04) failed on **six
hooks**, all fixers modifying files (exit via "pre-commit hook(s) made
changes"):

| Hook | CI evidence |
|---|---|
| trim trailing whitespace | Fixing 9 files (http_server.py, yue2/song, deep_select.py, nar_fast, modeling_vae, storage, cuda_graph, batched, fastpath) |
| fix end of files | Fixing yue2/__init__.py |
| isort | Fixing 16 files (experimental/yue2/http_api.py, deep_select.py, pipeline_configs/yue2.py, 5 model_specific_stages/yue2/*, test_server_yue2.py, 8 srt/models/yue2/*) |
| ruff | 3 errors fixed (2+1) |
| ruff format | 25 files reformatted (8+17) |
| codespell | exit 65: 10 findings (below) |

Every CI "Fixing" line maps to a PR-touched file — no unrelated upstream
file appears in the failure set.

## 2. Exact reproduction (isolated, CPU-only)

- Clean extract of the author's PR head `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`
  (offline tarball `sglang-ced0ef7d….tar.gz`, byte-identical source), fresh
  `git init` scratch repo — author's branch untouched.
- Pinned toolchain from the PR's own `.pre-commit-config.yaml`
  (pre-commit-hooks v6.0.0, isort 7.0.0, ruff v0.15.1, codespell v2.4.1)
  via `pre-commit run <hook> --files <35 PR files>`.
- Reproduction matches CI **exactly**: same 9 TW files, same EOF file, 16
  isort files, 3 ruff fixes, 25 ruff-format files, identical 10 codespell
  findings.

## 3. Codespell findings — reviewed individually (NOT accepted blindly)

| Location | Finding | Disposition |
|---|---|---|
| modeling_yue2.py:321,540,896,897 | `MoT ==> not` | **false positive** — MoT = Mixture-of-Transformers (YuE2 architecture, docstrings/comments) |
| yue2_pipeline.py:45 | `"mot": runtime.model` | **must not change** — `mot` is a live module-registry key consumed by `get_module("mot")`; rewriting breaks runtime lookup |
| yue2_pipeline.py:62,64 | `get_module("mot")` | same — live lookup key |
| ar.py:23 | `MoT ==> not` | false positive (docstring) |
| pipeline_configs/yue2.py:46 | `evalate ==> evaluate` | real typo in comment — **fixed** |
| sampling.py:15 | `suport ==> support` | real typo in comment — **fixed** |

Resolution: two typo fixes applied; `MoT,mot` appended to `.codespellrc`
`ignore-words-list` (the repo's existing list already contains dozens of
domain terms — established precedent, one-token change).

## 4. Behavior-preservation audit (the non-negotiable part)

Full AST comparison old→new across all 28 changed files, then manual
classification of every non-formatting delta:

| Delta class | Files | Safety argument |
|---|---|---|
| Import reorder only (isort) | 20 files | same symbol set, same module count; sorted-imports diff |
| Duplicate import lines consolidated | song.py (9→7 lines: two `from .fastpath` merged + redundant `from .protocol import ABC_END, MUSIC_END` subsumed by fuller import) | union of symbols identical |
| Unused import removed | test_server_yue2.py (`import sglang` before `from sglang...registry import …` in try/except) | from-import still loads the package; exception semantics unchanged |
| Import moved to module level | deep_select.py (`make_cpp_args` pulled out of parenthesized group to keep its inline comment) | same import target, module-level order irrelevant (no side-effect interleave — neighbors are stdlib/torch imports already at module level) |
| String annotation unquoted | request.py, yue2_loader.py (`-> "Yue2Request"` → `-> Yue2Request`) | both files have `from __future__ import annotations` (verified) → annotations never evaluated at runtime |
| Comment typos | 2 lines | not in AST |

Non-import AST structure: **SAME** for 26/28 files; the 2 "DIFFERS" are the
annotation unquoting above. `py_compile` clean on all 28.

## 5. Result

All six previously-failing hooks now **PASS** on the PR file set:

```
trailing-whitespace: Passed    isort: Passed
end-of-file-fixer: Passed      ruff: Passed
ruff-format: Passed            codespell: Passed
```

Patch: `patches/sglang_lint_fix_ced0ef7d.patch` (5,090 lines, 28 files +
.codespellrc; applies to `ced0ef7d`). Published branch:
`AIwork4me/sglang@fix/yue2-upstream-lint`, tip
`1a9f2d92a201b21242ca6c1bbe8a070189b0a913`, parent exactly `ced0ef7d`,
29 changed files (verified via compare API; created through the Git Data
API because git transport is blocked from this environment). The patch
file and the branch carry identical content.

## 6. Required author integration command (their branch, their push)

```bash
# inside the author's AMD-sglang-benchmark-fork add_yue2 checkout at ced0ef7d
git fetch https://github.com/AIwork4me/sglang.git fix/yue2-upstream-lint
git cherry-pick FETCH_HEAD   # single commit, mechanical only
git push                     # updates sgl-project/sglang#42106
```

(or `git apply patches/sglang_lint_fix_ced0ef7d.patch` + commit).

Do **not** bundle this with the ROCm compatibility PR (benchmark-fork#1) —
formatting stays separately reviewable, per repo convention.

## 7. Disclosure

- The CI lint runs `--all-files`; any residual failures on non-PR files
  would be pre-existing upstream debt — none appeared in the CI failure
  set, and our scoped fix deliberately touches only PR files + the
  one-line `.codespellrc` ignore-list append.
- The ruff-format hook in CI printed a second "17 files reformatted"
  invocation line; all `Fixing` paths shown in the log are PR files. Our
  local scoped run totals 25 reformatted PR files, matching 8+17.

## Gate

`SGLANG_LINT_FIX_REVIEWED` — reproduction is exact, fixes are mechanical +
AST-audited, codespell domain-term trap (`mot` module key) identified and
avoided rather than blindly "corrected".
