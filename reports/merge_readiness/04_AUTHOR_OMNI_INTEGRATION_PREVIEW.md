# 04 — Author Omni integration preview (disposable, non-destructive)

Performed 2026-10-16 in a disposable git worktree
(`/tmp/opencode/omni-integration-preview`, now removed from the author's
perspective — their branch was never touched). All operations used actual
GitHub commit objects; no file was hand-edited except the 8 documented
`# noqa` lines and the executable bit.

## 1. Inputs (exact)

| Item | Value |
|---|---|
| Author base (PR #2540 head) | `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` (add_yue2, unchanged) |
| PR #1 (ROCm reference path) | commits `50c91c08` → `eca7770f` (head; includes author-accepted comment revision) |
| PR #2 (long lyrics) | commits `4ad6658b` → `4c089d19` (head) |
| Ancestry | both PRs branch directly off `85ae4b73` (verified `merge-base` = base; direct parents) |
| Independence | still independent: neither merged into `add_yue2`; PR file sets disjoint (PR#1: fa3/fastpath/song/stages + platform-gate test; PR#2: config + cap test + fixture data) |

Note: verification required repairing our own analysis clone first — a stale
`.git/shallow` boundary was artificially marking `eca7770f` as a root commit
("refusing to merge unrelated histories"). GitHub's API confirms the true
parent chain; the fix was local-only to our clone.

## 2. Preview integration (exact SHAs)

```
075f1c62  preview-merge-1: integrate ROCm reference-path PR#1 (eca7770f)   [merge, no conflicts]
19efab35  preview-merge-2: integrate long-lyrics PR#2 (4c089d19)           [merge, no conflicts]
ae11c6ad  style(yue2): mechanical pre-commit fixes for omni Lint gate       [single commit]
```

**Preview integration SHA: `19efab35cf2167af4b07e69f3047f36a9e873768`**
**Preview integration+style SHA: `ae11c6ad246023494a4f55f89e852384e019f5b4`**

Combined delta vs `85ae4b73`: 8 files, +428/−6 source lines (identical to the
two PRs; tree-level verification: `git diff eca7770f HEAD -- <PR1 files>` = 0
and `git diff 4c089d19 HEAD -- <PR2 files>` = 0). The style layer adds 22
files +2,262/−798 (formatting only; see §5).

## 3. Checks performed

| Check | Result |
|---|---|
| Patch application | clean; zero conflicts (`git ls-files -u` empty at both merges) |
| Conflicting modifications | none — disjoint file sets; no overlapping hunks |
| Import correctness | `py_compile` on all touched files OK; tests import `sglang_omni.models.yue2.{fastpath,song,stages,fa3}` OK |
| Speech API contracts | `test_yue2_speech_input_cap.py` 13/13 — YuE2 `max_speech_input_chars=None`, other TTS models keep the generic 4096 default |
| Existing CUDA path | `test_yue2_platform_gates.py` 12/12 — CUDA dispatch branches unchanged (mocked platform; on-device H800 check remains report 05) |
| ROCm platform gates | same 12 tests — gates select reference ATen attention/reference sampler on ROCm |
| Other TTS model defaults | `test_model_capabilities.py` 37/37 (same count at base) |
| Total unit tests on final preview | **62 passed** (env-omni-rocm python 3.12, torch 2.12.0+rocm7.14.1; PYTHONPATH-shadowed preview tree — the validated editable env was NOT modified) |
| Formatting/lint | see §5 — 15/16 hooks green; 1 author-owned failure remains |

## 4. Behavior preservation evidence

- Source delta = exactly the two delivered PRs (tree-level zero-diff check).
- No FA2/sampling/batching refactor introduced; no new TopK implementation;
  the preview contains no code beyond PR#1 + PR#2 + formatting.
- The style layer was reviewed hunk-by-hunk: import hunks are pure
  reordering/alphabetization (same symbol set — e.g.
  `from .fastpath import (FastSampler, GraphSampler, _load_topk_backend,
  fast_sampler_available)`); def/class hunks are black line-re-wrapping with
  unchanged names; dict-literal hunks reformat the same keys/values.
- `py_compile` + full unit suite pass after the style layer.

## 5. Lint discovery (important for CI timing)

PR #2540 **as submitted** fails the omni `Lint` workflow on 5 hooks if
maintainers approve CI today: trim-trailing-whitespace, shebang-executable,
isort, black, and leading-underscore. The style commit `ae11c6ad` fixes the
first four mechanically across the PR's files (+ our 8 noqa lines).
`leading-underscore` still fails on **author-owned names** (~166 findings in
fastpath 60, cuda_graph 35, nar_fast 19, modeling_yue2 18, batched 10, nar 8,
modeling_vae 8, tokenization 4, sampling 4 …) — renames there cross module
boundaries (e.g. `_load_topk_backend` is imported by other yue2 modules) and
belong to the author; the repo-wide no-underscore policy landed upstream in
#2267/#2338/#2365 before this PR was opened.

Patch file: `patches/omni_style_ae11c6ad.patch` (apply after integrating
PR#1+PR#2).

## 6. Expected author action (exact, no invented remotes)

On the author's `add_yue2` (they own the branch; squash-merge via GitHub UI
or local merge — their choice):

1. Merge PR#1 (`eca7770f`) and PR#2 (`4c089d19`) into `add_yue2`.
2. Apply the style layer, either:
   - `git fetch https://github.com/AIwork4me/sglang-omni.git ae11c6ad && git cherry-pick ae11c6ad`, or
   - `git apply patches/omni_style_ae11c6ad.patch && git add -A && git commit`
     (cherry-pick is preferred; the commit message documents scope).
3. Optionally rename their leading-underscore names to satisfy the last lint
   hook (`python scripts/check_leading_underscore.py --fix` then grep callers,
   per the hook's own guidance).
4. Push `add_yue2` → PR #2540 updates → maintainer approves workflows →
   Lint runs green (after step 3) or red-with-one-known-reason (without).

## 7. Remaining H800 requirements (post-integration)

See report 05. The platform-gate tests are mocked-platform tests, not GPU
execution proof; the integrated commit needs one focused H800 smoke run.

## Gate

`OMNI_INTEGRATION_PREVIEW_PASS` — clean patch application, zero conflicts,
62/62 unit tests, tree-level identity with delivered PRs, lint state fully
characterized with author-owned residue explicitly scoped out.
