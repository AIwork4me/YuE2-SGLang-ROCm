# 07 — SGLang #42106 merge-conflict RCA (non-destructive preview)

Method note: the git transport from this environment cannot fetch the full
sglang repository (TLS RPC failures on large clones), so the merge preview
was computed **exactly** via GitHub data instead: merge-base from the
compare API, per-file commit queries for every PR file, blob fetches at the
three refs, and `git merge-file --diff3` 3-way merges. The author's branch
was never touched; no rebase, no force, nothing pushed.

## 1. Geometry

| Ref | SHA |
|---|---|
| PR head (ours) | `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` |
| Merge base | `ba68306256d64c53d302dc5d2f3be9e388af0738` (= PR's recorded base; branch is 3 commits ahead of it) |
| Theirs (current main) | 839 commits ahead of merge base |

## 2. Conflict surface

Of the PR's 35 changed files, exactly **2** were also modified on main since
the merge base (verified by per-path commit queries since `ba683062`):

| File | main commits touching it | 3-way merge result |
|---|---|---|
| `python/sglang/multimodal_gen/registry.py` | 4 | **1 conflicting hunk** |
| `python/sglang/multimodal_gen/runtime/entrypoints/http_server.py` | 3 | **auto-merges cleanly** (verified `git merge-file` exit 0; merged result `py_compile` OK) |

All other 33 PR files (the entire `srt/models/yue2/` tree, pipeline, stages,
configs, tests, `deep_select.py`) are untouched by main → no conflict
possible there. No deletions/renames of PR files on main. This fully
explains GitHub's `mergeable=false / dirty`.

## 3. The one conflict, classified

`registry.py`, inside the model-name → pipeline-class dict:

| Side | Content |
|---|---|
| base (ba683062) | `"fastvideo/fastvideo-fasth3-4-step-preview-v1-vsa-datafree": "FastH3Pipeline",` |
| ours (ced0ef7d) | inserts `"m-a-p/yue2-3b": "YuE2Pipeline",` directly above the fastvideo line |
| theirs (main) | replaces the fastvideo key with `"fastvideo/fastvideo-fasth3-8-step-v2": "FastH3Pipeline",` |

Classification: **adjacent-line registry-entry conflict** (taxonomy closest
to D-lite: independent entries colliding on neighboring lines; not an API
or architecture change).

**Reviewed resolution — keep both sides:**

```python
    "m-a-p/yue2-3b": "YuE2Pipeline",
    "fastvideo/fastvideo-fasth3-8-step-v2": "FastH3Pipeline",
```

Properties:
- Preserves upstream main functionality (renamed fastvideo key wins —
  upstream intentionally replaced the old preview model id).
- Preserves the author's YuE2 registration (the PR's functional core).
- `diff(resolved, main)` = exactly the one yue2 line — i.e., the resolution
  is "current main + author's entry", the minimal possible.
- Dict entries are independent; zero semantic interaction; `py_compile` OK.
- Reference blob: `patches/sglang_registry_conflict_resolved.py`
  (auto-merge preview for the other file:
  `patches/sglang_http_server_automerge_preview.py`).

Semantic check of the clean http_server.py merge: author side adds a guarded
experimental YuE2 route loader (`if _route_path.is_file()` — no-op when
`experimental/yue2/http_api.py` is absent); main side adds telemetry kwargs
and route-model prebuild in different regions. Independent; compiles.

## 4. Upstream-architecture drift assessment

839 commits of drift was checked for the PR's integration surface:
- `multimodal_gen` registry/pipeline/stage structure still exists on main
  (registry.py conflict is a data-entry edit, not structural).
- No API/signature break detected in the two overlapping files' diffs
  (additions on both sides, no signature changes around YuE2's insertion
  points).
- No migration proposal is needed: the author's integration matches the
  current main structure. This is a one-line-conflict PR from a git
  perspective.

## 5. Exact author procedure (their branch, their push — no rebase)

```bash
# inside AMD-sglang-benchmark-fork add_yue2 at ced0ef7d (+ lint commit)
git fetch https://github.com/sgl-project/sglang.git main
git merge FETCH_HEAD            # expect: conflict in registry.py ONLY
# edit python/sglang/multimodal_gen/registry.py conflict hunk to:
#     "m-a-p/yue2-3b": "YuE2Pipeline",
#     "fastvideo/fastvideo-fasth3-8-step-v2": "FastH3Pipeline",
git add python/sglang/multimodal_gen/registry.py
git commit                      # conventional merge commit message
git push                        # PR #42106 becomes mergeable
```

Then request `run-ci` (report 08). Conflict resolution does NOT by itself
make the PR mergeable with respect to reviews/CI — it only clears `dirty`.

## 6. Risk register

| Risk | Level | Mitigation |
|---|---|---|
| Registry resolution drops an upstream key | none | resolution = main + 1 line (byte-diffed) |
| http_server auto-merge semantic clash | low | regions independent; compile-checked; experimental route guarded by `is_file()` |
| Hidden conflicts beyond the 2 files | none | per-path commit enumeration over all 35 PR files |
| Lint regressions from merge | low | merge brings main's files (CI-clean) and PR files (fixed in report 06) |

## Gate

`SGLANG_CONFLICT_PLAN_REVIEWED` — single conflict, both-sides-preserving
resolution byte-verified against current main; author-only push path; no
history rewrite anywhere.
