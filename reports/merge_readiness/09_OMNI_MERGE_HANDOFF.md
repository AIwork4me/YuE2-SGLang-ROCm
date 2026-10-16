# 09 — Omni merge handoff (sgl-project/sglang-omni #2540)

**Recommended merge order (the whole story in five steps):**

1. Author merges yiakwy…/sglang-omni#1 (`eca7770f`) → `add_yue2` gains the
   ROCm reference path (+31/−6, platform gates).
2. Author merges yiakwy…/sglang-omni#2 (`4c089d19`) → long-lyrics input
   support (official WSB prompt 164 servable).
3. Author cherry-picks `ae11c6ad` from
   `AIwork4me/sglang-omni@preview/omni-yue2-integration-style` (or applies
   `patches/omni_style_ae11c6ad.patch`) → mechanical lint fixes for the omni
   Lint gate; then (author-owned) renames their leading-underscore names
   (~166 findings; repo policy #2267/#2338/#2365).
4. Author runs the focused H800 smoke test on the integrated commit
   (report 05).
5. Maintainer approves the six `action_required` workflows (Lint/Docs
   Check/Test Layout minimum; optionally `run-tts-ci`), one human review
   (FrankLeeeee already requested) → merge (squash, per ruleset).

## Exact SHAs

| Item | SHA |
|---|---|
| Official PR head | `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` |
| ROCm PR #1 head | `eca7770fe196fe970f7d847858a5f92444b75538` |
| Long-lyrics PR #2 head | `4c089d193f1186aeb40609ac4913273db9cdea95` |
| Integration preview (PR1+PR2 merged, clean) | `19efab35cf2167af4b07e69f3047f36a9e873768` |
| Preview + style layer | `ae11c6ad246023494a4f55f89e852384e019f5b4` (branch `preview/omni-yue2-integration-style`) |

## Verified evidence (AMD W7900D, real server)

- Full WildSongBench 384/384, strict audit FULL, zero structural problems:
  SongBench GA **6.7301** (full) / **6.7323** (selected-192); PER
  0.24819/0.17608 (full/selected micro); MuLan ≈ 0.5080; AMC ≈ 0.4059;
  Q3O not tested. PER uses a ROCm-adapted evaluator with disclosed ASR
  capping — no exact cross-vendor PER parity claimed.
- Serving (GPU batch 1): P50 E2E **217.3 s**, audio 223.0 s, real-time
  speed 1.030×, client E2E RTF 0.975, throughput ≈ 0.0046 req/s; sweep
  C=1..8 zero errors, RPS flat, P50 linear — serialized GPU execution
  disclosed as a measured limitation, not hidden.
- Cross-arm: same weights via original-SGLang ROCm path scored GA 6.731 —
  every SongBench dimension within ±0.002.

## What is NOT yet true (do not merge on these assumptions)

- The submitted head `85ae4b73` alone is **CUDA-verified only**; dual-vendor
  claims become real only after PR#1 integration.
- No CI has executed (all six workflows `action_required`) — including
  Lint, which would fail today (5 hooks; mechanical fix prepared).
- No H800 run exists on any integrated commit.

## Requested maintainer actions

1. Approve workflows (or at minimum Lint + Docs Check + Test Layout);
   `run-tts-ci` if a serving-surface signal is wanted.
2. Human review (FrankLeeeee requested; ruleset needs 1 approval; note
   `require_extra_approval_for_unattributed_changes` if anyone but the
   author pushes to the branch).
3. Note: there is no YuE2 CI model label today; YuE2-specific CI coverage
   = the unit tests arriving with PR#1/#2 + author's H800 smoke test.

Evidence root: `AIwork4me/YuE2-SGLang-ROCm` branch
`validation/gfx1100-rocm7141` (`reports/author_acceptance/`,
`reports/final_acceptance/`).
