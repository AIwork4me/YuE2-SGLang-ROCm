# 01 — Live PR and CI Matrix (refreshed 2026-10-16)

Read-only GitHub API inspection of all five PRs. Every SHA below was re-fetched
from the GitHub REST/GraphQL API on 2026-10-16 (~15:20 UTC). This report
supersedes the prior snapshot; deltas vs. the previous known state are marked
**[NEW]**.

## 1. Official SGLang-Omni PR #2540 — "Add yue2 [Port from SGLang]"

| Field | Value |
|---|---|
| URL | https://github.com/sgl-project/sglang-omni/pull/2540 |
| State | OPEN, not draft |
| Author | yiakwy-xpu-ml-framework-team |
| Head | `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` (fork branch `add_yue2`, unchanged since 2026-10-05T03:18:46Z) |
| Base | `main` (recorded base `353cf3535f8a67a020facc80aef93eba9f8ed5bc`; omni `main` tip now `2c23b68f4f763c14cfb845eadb4883a5e791b701`) |
| Mergeability | `mergeable=true`, `mergeable_state=blocked` — **no git conflicts**; blocked by required checks + review |
| Labels | none |
| Requested reviewers | FrankLeeeee |
| Submitted reviews | 2 × GitHub Copilot bot, COMMENTED only (2026-10-05) |
| Inline review threads | 0 (confirmed via GraphQL `reviewThreads`: empty) |
| Issue comments | 0 |
| Last activity | 2026-10-05T08:33:58Z — **no author or maintainer activity since** |

### CI state at head `85ae4b73`

Zero check-runs exist on the head commit. Six workflow runs were created
2026-10-05T03:44:16Z, **all concluded `action_required`** (workflow awaiting
maintainer approval — standard first-contribution fork-PR gating):

| Workflow | Run ID | Conclusion |
|---|---|---|
| XPU CI | 37260615544 | action_required |
| Test Layout | 37260615546 | action_required |
| Lint | 37260615543 | action_required |
| Docs Check | 37260615542 | action_required |
| CPU CI | 37260615550 | action_required |
| Omni CI | 37260615890 | action_required |

All six were created 2026-10-05T03:44:16Z (CPU CI 03:44:16, Omni CI 03:44:19);
**none executed a single job — these are approvals pending, not failures.**

### Blocker classification (per mission taxonomy)

| # | Blocker | Present? |
|---|---|---|
| 1 | Merge conflict | **NO** (mergeable=true) |
| 2 | Lint failure | **UNKNOWN** — Lint workflow never executed (not a failure) |
| 3 | Code/test failure | **NO** — no GPU/CI test ever ran |
| 4 | Missing run-ci-style label | YES (no CI labels on PR; also see #5) |
| 5 | GitHub `action_required` workflow approval | **YES — primary CI blocker** |
| 6 | Skipped GPU jobs | YES — consequence of #5/#4 |
| 7 | Missing human review | YES — only bot reviews; FrankLeeeee requested, none submitted |

## 2. Official SGLang PR #42106 — "Add yue2"

| Field | Value |
|---|---|
| URL | https://github.com/sgl-project/sglang/pull/42106 |
| State | OPEN, not draft |
| Author | yiakwy-xpu-ml-framework-team |
| Head | `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` (fork branch `add_yue2`, unchanged since 2026-10-04T08:22:27Z) |
| Base | `main` (recorded base `ba68306256d64c53d302dc5d2f3be9e388af0738`; upstream main has moved further) |
| Mergeability | `mergeable=false`, `mergeable_state=dirty` → **real git conflicts vs current main** |
| Labels | documentation, diffusion, jit-kernel (auto-labeler) |
| Inline review threads | 0 |
| Issue comments | 4 (see below) |

### CI state at head `ced0ef7d` (runs from 2026-10-04, unchanged — no newer runs exist)

| Workflow | Run ID | Conclusion | Interpretation |
|---|---|---|---|
| Lint | 37188915379 | **failure** | real pre-commit failure (job `lint`, step "Run pre-commit checks") |
| PR #42106 - Add yue2 (pr-test.yml) | 37188915580 | failure | run-ci gate not satisfied → test stages skipped; `pr-test-finish` failure is the gate marker |
| PR Test Extra | 37188915496 | failure | same gate (`pr-test-extra-finish` failure) |
| PR Test (AMD) | 37188915610 | failure | same gate — jobs **skipped**, not executed |
| PR Test Extra (AMD) | 37188915503 | failure | same gate |
| PR Test (MUSA/NPU/Arm64/XPU/MLX/Xeon) | … | failure | same gate, jobs skipped |
| PR Test (PPU) | 37188915497 | success | CPU-only suite that ran without gate |
| PR Test (sgl-router) | 37188915370 | success | ran |
| Auto Label PRs / PR States | … | success | housekeeping |

Check-runs at head confirm: `pr-test-finish`, `pr-test-extra-finish`,
`pr-test-amd-finish` = failure (gate markers); every actual test job =
`skipped`. **No AMD/NVIDIA GPU test ever executed — nothing red is a kernel or
model failure.**

### Comment timeline

| Date | Author | Substance |
|---|---|---|
| 2026-10-02 | yiakwy | cc @a43992899 |
| 2026-10-04 | **a43992899 (YuE2 original author)** | **[NEW since prior snapshot]** Independent end-to-end validation of this PR at earlier commit `e0683229`: 192×2 WSB, cot=full, YuE2-Vae-legacy decoder, frozen evaluator — SongBench GA 6.7146 vs native 6.7360 (−0.021), PER 8.15% vs 8.61%, MuLan/AMC at parity; DeepSelect graph sampler + fused NAR active. Explicitly does not cover HTTP serving/concurrency. |
| 2026-10-04 | yiakwy | reply/acknowledgement |
| 2026-10-16 | AIwork4me (us) | cross-reference: W7900 arm-B (Omni port) full WSB run — GA 6.730, every SongBench dimension within ±0.002 of arm-A; links `validation/gfx1100-rocm7141` evidence |

### Blocker classification

| # | Blocker | Present? |
|---|---|---|
| 1 | Merge conflict | **YES** (dirty vs current main) |
| 2 | Lint failure | **YES** (real pre-commit failure, run 37188915379) |
| 3 | Code/test failure | **NO EVIDENCE** — no gated test ever ran; PPU (CPU) suite passed |
| 4 | Missing `run-ci` label | YES |
| 5 | action_required approval | n/a for this repo (workflows ran) |
| 6 | Skipped GPU jobs | YES — all GPU stages skipped by gate |
| 7 | Missing human review | YES — no maintainer review yet (YuE2 author comment is positive signal) |

## 3. Author-branch contribution PRs (our three existing contributions)

All three are **still OPEN and unmerged**; author has **not** integrated any of
them. Head SHAs match the expected checkpoints exactly.

| PR | Base | Head | Expected head | Match | mergeable_state | CI on head |
|---|---|---|---|---|---|---|
| yiakwy…/sglang-omni#1 (ROCm reference) | `85ae4b73` | `eca7770fe196fe970f7d847858a5f92444b75538` | eca7770f | ✓ | unstable | only housekeeping `cancel` job |
| yiakwy…/sglang-omni#2 (long lyrics) | `85ae4b73` | `4c089d193f1186aeb40609ac4913273db9cdea95` | 4c089d19 | ✓ | unstable | only housekeeping `cancel` job |
| yiakwy…/AMD-sglang-benchmark-fork#1 (SGLang ROCm) | `ced0ef7d` | `def437fb7949f26bd1b06473882fd928757c6377` | def437fb | ✓ | unstable | housekeeping only |

"unstable" reflects the trivial housekeeping checks, not test failures.

## 4. Upstream repo movement **[NEW]**

- `sgl-project/sglang-omni` main tip is now `2c23b68f` — includes today's
  "[CI]: Restore slash commands for stage and model labels (#2873)" and recent
  docs-heading CI additions (#2867, #2872). The CI label system is now
  stage/model-label based (`run-tts-ci`, `run-tts-moss-…`, `run-all-ci`, …)
  resolved by `.github/scripts/resolve_ci_labels.py`; recognized slash commands
  are `/tag-run-ci-label`, `/rerun-failed-ci`, `/tag-and-rerun-ci`.
  **No YuE2 CI model label exists** (verified against `resolve_ci_labels.py`).
- Omni #2540 remains mergeable (no conflict) against the moved main.
- `sgl-project/sglang` main has advanced past `ba683062`; #42106 still dirty.

## 5. Conclusions

1. **Omni #2540** has no code-level blocker *on record*: it needs (a) maintainer
   workflow approval or CI labels to make checks execute, and (b) human review.
   Its lint status is unknown-until-run — local lint verification is therefore
   part of this handoff (report 04).
2. **SGLang #42106** has exactly two code-level blockers — git conflicts (dirty)
   and the pre-commit lint failure — plus the run-ci authorization gate. No
   executed test has ever failed.
3. The author has integrated **none** of our three contribution PRs; the
   integration preview (report 04) remains necessary.
4. Strongest new upstream-acceptance signal: the **YuE2 original author's
   independent accuracy validation** of the SGLang port (comment of 2026-10-04).
5. Nothing in the refreshed data changes mission priorities. No duplicate work
   is warranted.

## 6. Gate

`CI_BLOCKERS_CLASSIFIED` — classification performed from authoritative GitHub
API data (pulls API, check-runs API, actions runs API, GraphQL review threads).
Independent verification delegated to Reviewer B in report 11
(FINAL_INDEPENDENT_REVIEWS.md).
