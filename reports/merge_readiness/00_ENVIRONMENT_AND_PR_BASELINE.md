# 00 — Environment and PR Baseline (upstream merge-readiness mission)

Refreshed: 2026-10-26 (local time). All data re-verified live on this machine
and via the GitHub API / `git ls-remote`. Nothing is assumed from prior
reports; every previously pinned SHA was re-checked.

## 1. Machine baseline (PASS)

| Item | Value | Status |
|---|---|---|
| Host / OS | amd-HP-ZBook-Ultra, Ubuntu, kernel 6.17.0-1033-oem x86_64 | PASS |
| CPU / GPU | AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S (`gfx1151`, cap `(11,5)`) | PASS |
| VRAM | 32 GiB dedicated (34,359,738,368 B); ~1.1 GiB in use at audit | PASS |
| RAM / swap | 94 GiB total (88 GiB free at audit) / 8 GiB swap (unused) | PASS |
| Disk | 1.9 TB volume, 157 GiB free (92% used) — sufficient, monitored | PASS |
| Host ROCm | 7.2.1 (`/opt/rocm-7.2.1`) | PASS |
| PyTorch | 2.12.0+rocm7.14.1, `torch.version.hip` = 7.14.60850 (populated) | PASS |
| HIP execution | 512×512 GPU matmul on `cuda` device: synchronized, finite result | PASS |
| Python env | `environments/yue2` venv, Python 3.12.3 | PASS |
| sglang resolution | imports from `upstream/sglang` source tree, `0.0.0.dev1+gced0ef7d1.d20261011` | PASS |
| Model cache | `models/YuE2-3B` (6.8 GiB), `models/YuE2-Vae-legacy` (507 MiB) | PASS |
| GitHub CLI | authenticated as **AIwork4me** (active; scopes repo, workflow, gist, read:org) | PASS |

Environment constraints honored: no ROCm/driver/kernel/PyTorch changes were
made; the verified torch+HIP stack is untouched. `HSA_OVERRIDE_GFX_VERSION`
is not set. Network access to GitHub is flaky (bounded-retry loops used);
huggingface.co blocked → `HF_ENDPOINT=https://hf-mirror.com` when needed.

## 2. GitHub state refresh (2026-10-26) — every pinned head re-verified

### Upstream mains (MOVED since prior sessions — must rebase against these)

| Repository | main HEAD (2026-10-26) | Note |
|---|---|---|
| sgl-project/sglang | `d96c38633540842602acf768f9cdd599f75e7878` | advanced; conflicts must be re-resolved against this |
| sgl-project/sglang-omni | `5092197f0b736295ac3413f0ee29a4abd7d0e6a8` | advanced |

### PRs under mission scope

| PR | State | Head | vs mission pin |
|---|---|---|---|
| sgl-project/sglang#42106 "Add yue2" | OPEN, not draft | `add_yue2` @ `ced0ef7d1…` | **unchanged** (no author push since 2026-10-04; updatedAt 2026-10-25); `mergeable` UNKNOWN at query time (was CONFLICTING/DIRTY on 2026-10-13) |
| sgl-project/sglang-omni#2540 | OPEN, not draft | `add_yue2` @ `85ae4b7331…` | **unchanged** (updatedAt 2026-10-05) |
| sgl-project/sglang-omni#2875 (AIwork4me) | OPEN, not draft | `fix/yue2-long-lyrics` @ `4c089d19…`, base `main` | unchanged (updatedAt 2026-10-16); disposition task in Phase 4 |
| yiakwy…AMD-sglang-benchmark-fork#1 (ROCm compat) | OPEN, MERGEABLE, **not merged** | `def437fb…` | author has not integrated |
| yiakwy…sglang-omni#1 (ROCm compat) | OPEN, MERGEABLE, **not merged** | `eca7770f…` | author has not integrated |
| yiakwy…sglang-omni#2 (long lyrics) | OPEN, MERGEABLE, **not merged** | `4c089d19…` | author has not integrated |

### Author fork branch heads (re-verified via `git ls-remote`)

- `yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork` `add_yue2` =
  `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` (fork `main` = `2cf3ac51…`)
- `yiakwy-xpu-ml-framework-team/sglang-omni` `add_yue2` =
  `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9`

**Conclusion:** all author-owned heads are frozen exactly at the mission's
pins; the previously prepared contributions (3 compat PRs + 2 Omni style
commits `ae11c6ad`, `b91b9544`) are still open and un-duplicated upstream.
The dominant new work is resolving both YuE2 branches against the two
advanced upstream mains.

## 3. Local repository state

| Path | State | Treatment |
|---|---|---|
| `upstream/sglang` | detached HEAD @ `ced0ef7d`; benchmark-era working-tree modifications (quark quantization files) present | **preserved untouched** (historical benchmark evidence tree); integration happens in a separate worktree |
| `evidence/YuE2-SGLang-ROCm` | `main` @ `4612c20` == `origin/main`, clean | mission deliverables go here |
| `evidence` remote branch `handoff/yue2-upstream-merge-readiness` | @ `40bd59f` (contains `reports/final_merge_closure/01–10` via merged PR #4) | prior closure package — inputs to this mission, not to be rewritten |
| sglang-omni local clone | **absent** | to be created in Phase 3 (isolated, separate history) |
| `models/` | YuE2-3B + VAE cached locally | reused for Phase 2/3 GPU tests |

## 4. Prior work inventory (reuse, do not reimplement)

- SGLang ROCm guards (4 capability gates keyed on
  `is_deepselect_supported()`) — PR head `def437fb`; validated previously on
  W7900 and gfx1151 (see `docs/YUE2_UPSTREAM_AUTHOR_HANDOFF.md`).
- Prepared SGLang lint commit `1a9f2d9…` (AIwork4me fork).
- Omni ROCm PR `eca7770f`, Omni long-lyrics PR `4c089d19`, style commits
  `ae11c6ad` → `b91b9544`; integration rehearsal tree `363073e6` (pinned
  historical base `85ae4b73`), 76/76 tests, W7900 smoke, bit-identical rename
  proof.
- gfx1151 full WildSongBench evidence (384/384, SCORING_COMPLETE,
  evidence commit `038acf2`) — historical tree `ced0ef7`+patches; **not**
  evidence for new integration commits.

## 5. Blockers / risks at baseline

- GitHub network flakiness (mitigated: bounded retry loops; verified
  `ls-remote`/API reads).
- Disk at 92% (157 GiB free): two new repo clones + worktree fit; no large
  new downloads required (models cached).
- Upstream main movement is the core risk to resolve (Phases 1 and 3).

Status summary: environment PASS; PR baseline refreshed; no author-side
movement; proceeding to Phase 1 integration.

Post-audit disclosure (added 2026-10-27): all gfx1151 serving in reports
02/03/10 ran with a 4-file ROCm host-boot overlay applied to the working
tree (report 02 §overlay, report 10 §2) — the overlay is not part of any
YuE2 branch; upstream candidate: `AIwork4me/sglang:fix/hip-host-import-guards`.
