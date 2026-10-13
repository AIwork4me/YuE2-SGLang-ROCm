# Phase 1: Independent Upstream State Audit (read-only)

Audit time: 2026-10-13 (UTC). Auditor account: AIwork4me (read-only `gh api` / `gh pr view`; no writes, no comments).
All facts below are direct API responses; no speculation.

---

## PR 1 — yiakwy-xpu-ml-framework-team/sglang-omni#1 (our minimal ROCm PR)

Source: `gh api repos/yiakwy-xpu-ml-framework-team/sglang-omni/pulls/1`

| Field | Value |
|---|---|
| Title | fix(yue2): enable ROCm reference path without regressing CUDA fast paths |
| Author | AIwork4me |
| State | open, **isDraft = true**, not merged |
| Created / Updated | 2026-10-13T05:38:51Z / 2026-10-13T07:14:23Z |
| Base | `add_yue2` @ `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` (fork repo yiakwy-xpu-ml-framework-team/sglang-omni) — **matches expected** |
| Head | `fix/yue2-rocm-reference` @ `50c91c0888312ae784d3c42d9536665aa517dd9d` (AIwork4me/sglang-omni) — **matches expected** |
| maintainer_can_modify | true |
| mergeable / mergeStateStatus | true (no git conflict) / **UNSTABLE** (graphql `mergeStateStatus`; REST `mergeable_state`) |
| reviewDecision | null (no required-review policy on this fork repo) |
| Requested reviewers / teams | none / none |
| Reviews (pulls/1/reviews) | **0 total** (0 human, 0 bot) |
| Inline review comments (pulls/1/comments) | 0 |
| Issue comments (issues/1/comments) | 0 |
| CI checks | `gh pr checks`: "no checks reported on the 'fix/yue2-rocm-reference' branch"; graphql `statusCheckRollup` = null; combined commit status for head SHA = `pending` with 0 statuses |
| Commits | 1: `50c91c0` "fix(yue2): enable ROCm reference path without regressing CUDA fast paths" (author AIwork4me) |
| Size / files | +237/−6, 5 files |

Files changed:
- `sglang_omni/models/yue2/fa3.py`
- `sglang_omni/models/yue2/fastpath.py`
- `sglang_omni/models/yue2/song.py`
- `sglang_omni/models/yue2/stages.py`
- `tests/unit_test/models/test_yue2_platform_gates.py`

Branch protection on base `add_yue2`: `GET .../branches/add_yue2/protection` → 404 Not Found (no protection rules).

---

## PR 2 — sgl-project/sglang-omni#2540 (author's "Add yue2 [Port from SGLang]")

Source: `gh api repos/sgl-project/sglang-omni/pulls/2540`

| Field | Value |
|---|---|
| State | open, not draft, not merged |
| Created / Updated | 2026-10-05T03:44:11Z / 2026-10-05T08:33:58Z (no update since Oct 5) |
| Base | `main` @ `353cf3535f8a67a020facc80aef93eba9f8ed5bc` (sgl-project/sglang-omni) |
| Head | `yiakwy-xpu-ml-framework-team:add_yue2` @ `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` — **identical SHA to PR1's base** (base has not drifted) |
| mergeable / mergeStateStatus | true / **BLOCKED** |
| reviewDecision | **REVIEW_REQUIRED** |
| Requested reviewers | FrankLeeeee |
| Reviews | 2, both bot (`copilot-pull-request-reviewer[bot]`, COMMENTED, "quota limit") — **0 human reviews** |
| Inline review comments | 0 |
| Issue comments | 0 |
| CI checks | "no checks reported on the 'add_yue2' branch"; graphql `statusCheckRollup` = null |
| Commits | 2: `7d34d6e` "migrate yue2 supprot from SGLang to SGLang-Omni", `85ae4b7` "update" |
| Files | 27 (yue2 model dir + examples/run_yue2_generate.py + tests/unit_test/models/test_model_capabilities.py + MIGRATION.md/README.md) |

---

## PR 3 — sgl-project/sglang#42106 (original sglang "Add yue2")

Source: `gh api repos/sgl-project/sglang/pulls/42106`

| Field | Value |
|---|---|
| State | open, not draft, **not merged** (merged_at null, merge_commit_sha null) |
| Created / Updated | 2026-10-01T17:42:15Z / 2026-10-04T08:50:24Z |
| Base | `main` @ `ba68306256d64c53d302dc5d2f3be9e388af0738` |
| Head | `yiakwy-xpu-ml-framework-team:add_yue2` (repo AMD-sglang-benchmark-fork) @ `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` |
| mergeable / mergeStateStatus | **false / DIRTY** (merge conflicts with base) |
| reviewDecision | REVIEW_REQUIRED |
| Requested reviewers | 17 (HaiShaw, yuan-luo, merrymercy, yizhang2077, mickqian, ping1jing2, BBuf, niehen6174, AgainstEntropy, kevin-mii, HydraQYH, ch-wan, DarkSharpness, celve, mmangkad, yichiche, b8zhong) |
| Reviews | 1 bot only (Copilot, quota-limited COMMENTED) — 0 human reviews |
| Inline review comments | 0 |
| Issue comments | 3, all human: yiakwy cc @a43992899 (Oct 2); a43992899 (YuE2 author) — end-to-end eval on Oct 3 at `e0683229...`, "accuracy broadly aligned with native YuE2 implementation" (Oct 4); yiakwy reply (Oct 4) |
| CI checks | statusCheckRollup state **FAILURE**; failing: `lint` (2m47s), multiple `pr-gate`/`call-gate`, `pr-test-*-finish` wrapper jobs; many matrix jobs "skipping" (gated behind `run-ci` label) |
| Commits / files | 3 commits, 35 files |

---

## Branch & duplicate verification

- `repos/yiakwy-xpu-ml-framework-team/sglang-omni/branches` (paginated): exactly **2 branches** — `add_yue2` @ `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` (**unchanged**, matches expected base) and `main` @ `6cafa0c491c8ff8826bc649e1fd815808b7fbef0`. **No new branches.**
- `repos/AIwork4me/sglang-omni/branches`: `fix/yue2-rocm-reference` @ `50c91c0888312ae784d3c42d9536665aa517dd9d` (**matches expected HEAD**). Many unrelated branches exist; only one yue2-rocm branch.
- ROCm already in author's add_yue2? `contents/sglang_omni/models/yue2/{stages,song,fastpath,fa3}.py?ref=add_yue2` decoded: `is_rocm` occurrences = **0 in all four files**. `stages.py:10` imports `current_platform`; `stages.py:46` still gates `if not current_platform.is_cuda():` → upstream add_yue2 contains **no ROCm handling**; PR1 is not redundant.
- Duplicate ROCm PRs? `gh pr list --repo yiakwy-xpu-ml-framework-team/sglang-omni --state all --search rocm` → only PR#1 itself. `gh pr list --repo AIwork4me/sglang-omni --state all` → **empty**. **No duplicates on either fork.**

---

## MERGE BLOCKERS (PR #1, actual, evidence-cited)

1. **Draft state (hard GitHub block).** REST `draft: true`; graphql `isDraft: true`. GitHub refuses to merge draft PRs regardless of mergeability; author must mark "Ready for review".
2. **Zero reviews / no approval.** `pulls/1/reviews` = `[]`; `requested_reviewers` = `[]`; no inline or issue comments. No human or bot approval exists. (No branch protection on `add_yue2` — 404 — so no repo-policy review requirement, but there is likewise no approving review.)
3. **No CI verification of any kind.** `mergeStateStatus: UNSTABLE` with `statusCheckRollup: null`; `gh pr checks`: "no checks reported"; combined head-SHA status `pending` with 0 statuses. Nothing on GitHub validates the +237/−6 change.
4. **(Contextual, not mechanical) Base chain unmerged.** PR1's base `add_yue2` is itself only a feature branch; the PR carrying it upstream (sgl-project/sglang-omni#2540) is `BLOCKED` with `reviewDecision: REVIEW_REQUIRED` (0 human reviews; sole requested reviewer FrankLeeeee hasn't reviewed; PR stale since 2026-10-05). PR1 itself reports `mergeable: true` against the unmoved base, so this is not a git-level blocker, but the ROCm patch cannot reach sgl-project/sglang-omni `main` until #2540 is reviewed/merged.

Non-blockers (verified clean): head SHA matches expectation; base SHA matches expectation (no drift); no merge conflict; no duplicate ROCm PR; upstream add_yue2 contains no overlapping ROCm changes.

---

PHASE1_VERDICT: BLOCKED — PR#1 is a draft with zero reviews and zero CI validation (hard blockers), and its upstream carrier PR sgl-project/sglang-omni#2540 is review-blocked (REVIEW_REQUIRED, no human reviews).
