# 10 — SGLang merge handoff (sgl-project/sglang #42106)

## PR identity

- Official PR: sgl-project/sglang#42106, head `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`
  (author branch `add_yue2` in yiakwy…/AMD-sglang-benchmark-fork).
- Status: OPEN, `mergeable=false/dirty`, labels documentation/diffusion/jit-kernel,
  no `run-ci`, no maintainer review yet; 4 comments (incl. the YuE2 original
  author's independent accuracy validation at `e0683229` — SongBench GA
  6.7146 vs native 6.7360, "broadly aligned").

## Validation history (both vendors, separate campaigns)

| Arm | Hardware | Scope | Key results |
|---|---|---|---|
| Author CUDA (NVIDIA) | H800 SuperPod | single-shot pytest; WSB 384 (paper-protocol comparison); 7.0 s full-song BS=1 / 1.81 req/s statements | GA 6.721 full vs paper 6.730; PER 8.29% vs paper 8.44% (PR body) |
| YuE2 original author | NVIDIA | independent WSB 384 at `e0683229`, frozen evaluator | GA 6.7146 vs native reference 6.7360; PER 8.15% vs 8.61% (PR comment) |
| Our AMD W7900 (ROCm 7.14.1) | Radeon PRO W7900 | full WSB 384/384 via `sglang serve` + benchmark-fork#1 patch, strict audit FULL | GA 6.731; PER 0.1701 selected / 0.2275 unselected micro; MuLan 0.5099; AMC 0.4052 |

Cross-vendor note: PER figures are not comparable across evaluator
revisions/ASR caps; SongBench/MuLan/AMC agree within tolerance across all
arms. No exact hardware equivalence claimed.

## Actual blockers (three, all characterized)

1. **Lint** (run 37188915379): 6 hooks failed — reproduced exactly on a
   clean `ced0ef7d` extract with the pinned toolchain; **reviewed minimal
   fix**: `patches/sglang_lint_fix_ced0ef7d.patch` (28 files + 1-line
   `.codespellrc` ignore append for the MoT/mot domain terms — `mot` is a
   live module-registry key and must not be "corrected" to `not`).
   AST-audited behavior-preserving. Published as
   `AIwork4me/sglang@fix/yue2-upstream-lint` (commit `1a9f2d92`, parent
   `ced0ef7d`) — author cherry-picks, does not mix with ROCm PR.
2. **Merge conflict**: exactly one hunk, `python/sglang/multimodal_gen/registry.py`
   (author's `"m-a-p/yue2-3b": "YuE2Pipeline",` insertion vs upstream's
   fastvideo key rename). Resolution = keep both (byte-verified:
   resolved file = current main + the single yue2 line;
   `patches/sglang_registry_conflict_resolved.py`). `http_server.py`
   auto-merges cleanly (preview verified). Author merges `main` into
   `add_yue2`, resolves the one hunk, pushes.
3. **run-ci gate**: `call-gate/pr-gate → "Require run-ci label"` — no
   maintainer has labeled; all GPU jobs skipped (never executed, never
   failed). A maintainer or CI_PERMISSIONS-listed user adds `run-ci`.

## Recommended safe author actions (order)

1. Cherry-pick lint fix (`1a9f2d92`).
2. Merge `main`, resolve registry.py per report 07, push.
3. Optionally integrate benchmark-fork#1 (`def437fb`) as a separate commit.
4. Ask one maintainer for `run-ci`; rerun CI; address only genuine failures.
5. Request human review (YuE2-author validation comment is a strong signal
   to reference).

## Separation guarantees

- Formatting ≠ ROCm compatibility ≠ conflict resolution — three separate,
   individually revertable commits/PRs.
- MANUAL_ROCM_VALIDATION (W7900 campaigns) is never presented as
   OFFICIAL_SGLANG_CI (nothing has executed there yet).
- Same-commit dual-vendor verification does not exist until the author runs
   the H800 check on the integrated head (report 05, SGLang-side variant
   via their own `test_server_yue2.py` command).
