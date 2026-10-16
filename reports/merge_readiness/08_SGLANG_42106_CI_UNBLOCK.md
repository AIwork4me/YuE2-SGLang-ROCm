# 08 — SGLang #42106 CI unblock checklist

Refreshed 2026-10-16. Prior verified state **unchanged**: the only executed
CI at head `ced0ef7d` is still the 2026-10-04 run set; no newer runs exist.

## 1. Current gate state (authoritative)

- Failing step: run 37188915580 (`.github/workflows/pr-test.yml`), job
  `call-gate / pr-gate`, step **"Require run-ci label (optional)"** — the
  PR carries labels `documentation, diffusion, jit-kernel` and **no
  `run-ci`**.
- Consequence: `pr-test-finish`, `pr-test-extra-finish`,
  `pr-test-amd-finish` report failure as gate markers while **every actual
  test job is `skipped`**. No AMD/NVIDIA GPU test ever executed — nothing
  red is a code failure.
- Lint (run 37188915379) fails on real pre-commit issues → fixed and
  reviewed in report 06 / `patches/sglang_lint_fix_ced0ef7d.patch`.
- Mergeability: `dirty` (single registry.py conflict → reviewed resolution
  in report 07).

## 2. Who can act

| Action | Who |
|---|---|
| Add `run-ci` label | sglang maintainers with write access |
| Slash-command CI controls | users in `.github/CI_PERMISSIONS.json` (268 entries, incl. FrankLeeeee, zhaochenyang20, yinghai, …) |
| Author | cannot self-label; can push fixes and request the label |

## 3. Author checklist (exact order)

1. **Apply the reviewed lint patch** — cherry-pick single commit from our
   published `fix/yue2-upstream-lint` (from `ced0ef7d`) or
   `git apply patches/sglang_lint_fix_ced0ef7d.patch` + commit.
2. **Resolve the merge conflict** per report 07 (merge `main` into
   `add_yue2`; one hunk in `registry.py`; keep both the yue2 entry and
   upstream's renamed fastvideo key), push.
3. Optionally integrate the ROCm compatibility PR
   (yiakwy…/AMD-sglang-benchmark-fork#1, `def437fb`) — separate commit,
   separate review concern, NOT bundled with formatting.
4. Confirm PR shows `mergeable=true` (GitHub recomputes after push).
5. **Request `run-ci`** from a maintainer (one comment, one account; do not
   group-ping). Suggested text in report 10.
6. Rerun/rerun-failed CI once labeled.
7. Address only *genuine* failures (if any execute for the first time).
   Note: YuE2 model-level tests need `SGLANG_TEST_YUE2=1` + model weights
   and are not part of the standard matrix — the author's H800 smoke test
   (report 05, adapted to the SGLang side via their own
   `test_server_yue2.py` command) remains the model-level validation.
8. Request human maintainer review.

## 4. Classification discipline (do not conflate)

| Observed | Correct reading |
|---|---|
| `pr-test-finish: failure` | gate marker for missing `run-ci` — not a test failure |
| AMD jobs `skipped` | policy skip — **not** "AMD tests failed" |
| W7900 manual benchmark PASS | `MANUAL_ROCM_VALIDATION` — never presentable as `OFFICIAL_SGLANG_CI` |
| Lint failure | real; fixed by reviewed mechanical patch |
| `dirty` | real; single-conflict resolution prepared |

## 5. Evidence separation

- **MANUAL_ROCM_VALIDATION** = W7900 WSB 384/384, BS=1/concurrency sweep
  (evidence repo `validation/gfx1100-rocm7141`).
- **OFFICIAL_SGLANG_CI** = sgl-project workflows under `run-ci` — has never
  executed for this PR. No public statement may blur the two.

## Gate

`SGLANG_CI_HANDOFF_READY` — every blocked state traced to its mechanism
(label gate / lint / conflict); no permission claimed that we do not have;
no label applied by us anywhere.
