# H800 Validation Handoff — Corrected Git Preparation (2026-10-13)

Status: **Published** as a focused documentation-only edit to PR #1's body
(five-file code patch untouched; no duplicate comment posted — the original
H800 request comment of 2026-10-13T11:38Z stands).

## Why the previous instructions were wrong

The old body said:

    git fetch origin add_yue2 fix/yue2-rocm-reference

`add_yue2` lives on the AUTHOR's origin, but `fix/yue2-rocm-reference` lives
on **AIwork4me/sglang-omni** — the author's origin does not contain our
branch, so the fetch fails or, worse, resolves an unrelated ref.

## Corrected sequence (validated in a disposable local Git test repo)

Run in the author's sglang-omni clone:

```bash
git fetch origin add_yue2
BASE_SHA=$(git rev-parse FETCH_HEAD)

git fetch https://github.com/AIwork4me/sglang-omni.git fix/yue2-rocm-reference
PATCH_SHA=$(git rev-parse FETCH_HEAD)
test "$PATCH_SHA" = "50c91c0888312ae784d3c42d9536665aa517dd9d"   # pinned

git worktree add --detach /tmp/yue2-h800-check "$BASE_SHA"
git -C /tmp/yue2-h800-check cherry-pick "$PATCH_SHA"
```

Validation performed (2026-10-13, /tmp/opencode/git-h800-test, local bare
repos simulating author repo + fork): base fetch, fork fetch by URL,
FETCH_HEAD pinning, detached worktree creation, cherry-pick — all succeed;
re-applying the same patch correctly reports "nothing to commit" (the
already-integrated signal).

## Guardrails for the author

- If the patch is already integrated into `add_yue2`, cherry-pick becomes
  empty — do not apply twice.
- If HEADs have moved, inspect the relationship (`git log --oneline
  BASE_SHA..PATCH_SHA`) before trusting the pinned SHA.
- Operate only in the detached worktree; never on the author's active
  checkout.
- Import `sglang_omni` from the worktree (e.g. `pip install -e . --no-deps`),
  not a preinstalled older copy.
- Keep the existing CUDA PyTorch install; do NOT install ROCm wheels.

## What to test on H800

1. Real `sgl-omni serve` API with `SGLANG_YUE2_VAE_DIR` set.
2. Real NVIDIA H800 execution of the pinned commit.
3. `POST /v1/audio/speech` with the PR body's curl (seed 831001, cot=full).
4. HTTP 200 + valid 48 kHz stereo WAV (AR/NAR/VAE all complete).
5. Expected NVIDIA fast-path dispatch in logs (DeepSelect / fast sampler /
   step graph active) — the gates are no-ops on CUDA.
6. No new exceptions / no CUDA regression on the platform-gate test suite.

Identical audio SHA256 across vendors is NOT expected or required. Record the
exact validated commit SHA + environment (torch build, driver) in the reply.

## Gate

H800_HANDOFF_VALIDATED: instructions syntactically validated, published on
PR #1 body, cross-repo refs correct. Real H800 execution remains pending on
the author (no H800 hardware on our side — must not be claimed as PASS).
