# 06 — Author integration (rehearsed end-to-end)

## Exact inputs

| Step | Object | SHA |
|---|---|---|
| 1. Base | author `add_yue2` (= PR #2540 head) | `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` |
| 2. Merge ROCm PR #1 | head | `eca7770fe196fe970f7d847858a5f92444b75538` |
| 3. Merge long-lyrics PR #2 | head | `4c089d193f1186aeb40609ac4913273db9cdea95` |
| 4. Cherry-pick style commit | `AIwork4me/sglang-omni@preview/omni-yue2-integration-style` | `ae11c6ad246023494a4f55f89e852384e019f5b4` |
| 5. Cherry-pick naming closure | `AIwork4me/sglang-omni@fix/yue2-omni-leading-underscore-closure` | `b91b95440cf3ce9b6d83f6593d85c91aadffbfd2` |

Step 5 MUST be applied after step 4 (the closure commit is a direct child
of ae11c6ad; applying it without the style layer is not the tested object).

## Author commands (their branch, their push)

```bash
# inside yiakwy-xpu-ml-framework-team/sglang-omni, branch add_yue2 at 85ae4b733
git merge --no-ff eca7770fe196fe970f7d847858a5f92444b75538   # PR #1 (or merge the GitHub PR)
git merge --no-ff 4c089d193f1186aeb40609ac4913273db9cdea95   # PR #2 (or merge the GitHub PR)
git fetch https://github.com/AIwork4me/sglang-omni.git ae11c6ad246023494a4f55f89e852384e019f5b4
git cherry-pick FETCH_HEAD                                    # mechanical style layer
git fetch https://github.com/AIwork4me/sglang-omni.git b91b95440cf3ce9b6d83f6593d85c91aadffbfd2
git cherry-pick FETCH_HEAD                                    # naming closure
git push                                                      # PR #2540 updates
```

(Steps 2–3 may equivalently be done by merging PRs #1 and #2 in the GitHub
UI; the tree outcome is identical — verified below.)

## Rehearsal result (disposable worktree, 2026-10-16)

Every step applied with ZERO conflicts (`git ls-files -u` empty throughout).
Final integrated **tree hash `363073e688fa9761c72f029a1022a87405b1aead` =
tree of the tested branch b91b95440, byte-identical** — the tree offered to
the author is exactly the tree that passed all checks:

- leading-underscore checker: exit 0
- focused unit suite: 76/76 pass
- no duplicate modifications, no missing imports (all 22 yue2 modules import)

Full log: `OMNI_AUTHOR_INTEGRATION_REHEARSAL.md`.

## After integration (author/maintainer)

1. Maintainer approves workflows → Lint runs (expected green locally-proven
   surface), Docs Check, Test Layout (+ optionally run-tts-ci).
2. One focused H800 smoke on the integrated commit (report 08).
3. One human review (FrankLeeeee already requested; squash-merge per ruleset).
