# Omni author integration rehearsal (Phase 12, 2026-10-16)

Disposable worktree at author add_yue2 HEAD; every step below executed with
real git objects; author branches untouched.

## Steps and results

| Step | Command | Result |
|---|---|---|
| 1 | detach at `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` | OK |
| 2 | `git merge --no-ff eca7770fe196fe970f7d847858a5f92444b75538` | clean, 0 conflicts |
| 3 | `git merge --no-ff 4c089d193f1186aeb40609ac4913273db9cdea95` | clean, 0 conflicts |
| 4 | `git cherry-pick ae11c6ad246023494a4f55f89e852384e019f5b4` | clean |
| 5 | `git cherry-pick b91b95440cf3ce9b6d83f6593d85c91aadffbfd2` | clean |

`git ls-files -u` empty at every point (no unresolved conflicts); no
duplicate modifications (final tree equals the tested tree byte-for-byte —
a duplicate application would differ).

## Final integrated state

- Rehearsal HEAD `1d11362d0`, **tree `363073e688fa9761c72f029a1022a87405b1aead`**
- Tested branch `b91b95440` tree: `363073e688fa9761c72f029a1022a87405b1aead`
  → **IDENTICAL**. The tree offered to the author is exactly the tested tree.
- leading-underscore checker: exit 0.
- Focused suite on the rehearsal tree (PYTHONPATH-shadowed): 76/76 pass.
- All 22 yue2 modules import (model registration/capability surface intact —
  capabilities JSON logged by the serving launcher in the smoke run).

## Order-of-operations note for the author

The naming-closure commit (step 5) must be applied AFTER the style commit
(step 4): it is a direct child of ae11c6ad and its context assumes the
style layer. Steps 2–3 may be replaced by merging GitHub PRs #1 and #2
(reviewer C additionally proved merge-tree equality: merge(85ae4b73,
eca7770f) tree `0002fb3c` == tree(075f1c62); + 4c089d19 tree `7fdead12` ==
tree(19efab35)). Cherry-picking only b91b95440 WITHOUT steps 2–4 is not the
tested object and is expected to conflict.

## Known limitations

- Rehearsal commits differ in SHA from our branch (different parents/committer
  context) — expected; the TREE is the artifact, and it is identical.
- GitHub squash-merges of PRs #1/#2 would produce different commit IDs than
  these merges; the report-06 commands avoid that by using direct merges or
  the pinned SHAs.
