# W7900 RC4 — Git Baseline (M0.3)

Captured: 2026-11-22T13:38Z (live, not from stale reports)

## Local checkout

- Path: `/workspace/YuE2-SGLang-ROCm`
- Previous branch at session start: `fix/w7900-fresh-image-resume-hardening` @ `fee027d` (clean tree)
- Remotes:
  - fetch: `https://gh-proxy.org/https://github.com/AIwork4me/YuE2-SGLang-ROCm.git`
  - push:   `https://github.com/AIwork4me/YuE2-SGLang-ROCm.git`

## Live remote state (gh + git fetch, 2026-11-22T13:34Z)

- PR #16 (DRAFT, OPEN): head `mission/joint-blog-rc2` @ `48d1cb64fa2b4653ee40606a8dfbe3593c5b0b6f`, base `integration/joint-blog-rc`
  - Matches the mission's "last observed PR #16 HEAD" exactly — no remote drift since RC3.
- Open PRs: #8, #9, #10, #11, #12, #13, #14, #15, #16 (all DRAFT).
- `origin/main` @ `ba99c4d` (untouched by this mission).

## RC4 branch

- Created: `mission/w7900-rc4-repro-reliability` from `48d1cb6` (verified PR #16 HEAD)
- Ancestry: contains the full RC2/RC3 lineage incl. `reports/w7900_rc3/`
- Stacked-PR plan: target `mission/joint-blog-rc2` (actual PR #16 head branch)

## Rules honored

- No force-push; no modification of `main`; no merge/close of #16/#15; no external messages.
- RC4 work is isolated from PR #16 (it keeps Engineering GO state from RC3).
