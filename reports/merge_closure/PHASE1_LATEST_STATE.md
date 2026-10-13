# PHASE 1 — LATEST STATE (source-of-truth refresh)

Refreshed: 2026-10-13T12:45Z (all data re-verified live; GitHub API via `gh`,
git ls-remote, local repos, live /proc). Independent subagent verification of
PR states/SHAs: see `phase1_verification.md` (bottom).

## 1. Our minimal ROCm PR #1 — yiakwy-xpu-ml-framework-team/sglang-omni#1

- URL: https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1
- State: OPEN, **not draft** (Ready for Review), mergeable: MERGEABLE,
  mergeStateStatus: UNSTABLE (no required checks defined), no reviews, no
  review threads, statusCheckRollup: empty.
- head: `fix/yue2-rocm-reference` @ **50c91c0888312ae784d3c42d9536665aa517dd9d**
  (fork AIwork4me/sglang-omni branch verified at the same SHA via API).
- base: `add_yue2` @ 85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9 (author branch,
  unchanged since PR creation).
- Comments: exactly ONE — our H800 request (2026-10-13T11:38:28Z,
  issuecomment-6144689787). No author reply yet. No duplicate was posted.
- **Known defect in PR body**: Git prep line
  `git fetch origin add_yue2 fix/yue2-rocm-reference` is unreliable (the
  second ref lives on AIwork4me/sglang-omni, not the author's origin).
  Focused documentation-only body edit scheduled (Phase 4). Five-file code
  patch untouched.

## 2. Official Omni PR — sgl-project/sglang-omni#2540

- State: OPEN, not draft, mergeable: MERGEABLE, mergeStateStatus: BLOCKED
  (review requirements), author: yiakwy-xpu-ml-framework-team.
- head `add_yue2` @ **85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9** — UNCHANGED
  (no author push since 2026-10-05T08:33:58Z). Not merged.
- **The author has NOT merged, cherry-picked, or independently implemented
  equivalent ROCm changes** (head SHA identical; no new commits; PR #1 has no
  reviews/comments from the author).

## 3. Original SGLang PR — sgl-project/sglang#42106

- State: OPEN, not draft, **mergeable: CONFLICTING** (mergeStateStatus
  DIRTY) vs sgl-project/sglang main. head `add_yue2` @
  **ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f** — matches the frozen
  `sglang_commit` in the W7900 run_config. Not merged; no movement since
  2026-10-04.

## 4. Evidence repository — AIwork4me/YuE2-SGLang-ROCm

Remote branch SHAs (git ls-remote, verified after this session's pushes):

| branch | remote SHA | note |
|---|---|---|
| main | e05fd14ae9bd1b941592e518630eea6dce28f73d | unchanged |
| handoff/omni-add_yue2-rocm-pr | **64b16e9d5b1bc9c970a84c57b4d9e320dafbb1f4** | expected closure a438c299… + v2 scorer commit (this session) |
| validation/gfx1100-rocm7141 | **64b16e9d5b1bc9c970a84c57b4d9e320dafbb1f4** | aligned to same SHA this session (was 41427c7a) |
| evidence/omni-http-gfx1100 | f000a8596af91f9ed102f42ddbe3fc5f3ff1d180 | HTTP E2E PASS evidence (short + full) |

Branch reconciliation performed this session: the local checkpoint chain
(41427c7 → a438c29) was fast-forwarded onto remote validation so handoff and
validation share HEAD — all future checkpoint/scoring pushes fast-forward.

## 5. W7900 workload state (live)

- Generation driver PID 493545 (run_wsb.py, resumed 08:57Z) — HEALTHY,
  actively finalizing candidates; manifest 355/384 unique complete at 12:45Z.
- Generation server PID 487670 (`sglang serve` 127.0.0.1:31000) — HEALTHY.
- Identity receipt captured WITHOUT restart or signal:
  `run-state/server-identity.json` (pid 487670, uid 0, starttime 918563136,
  argv sha256, unique owner of the 31000 listen socket, run_id attributed).
- Milestone watcher PID 494130 — CPU-only, healthy.
- Old v1 scoring scheduler PID 494132 — **safely stopped 12:44Z** (stage-1
  wait loop; SIGTERM to exact PID; receipt preserved); v1 script renamed
  `.v1-retired-unsafe-pkill`.
- Replacement v2 scheduler PID **548480** — WAITING_FOR_384, lock owner
  verified, watches the existing run_id/run dir, cannot regenerate candidates.
- Redundant queued GPU smoke watcher PID 430873 — **stopped 12:22Z** (its
  purpose was already fulfilled by the 08:19Z HTTP E2E PASS; it would have
  raced the scoring pipeline for the GPU exactly at 384). Receipt preserved.
- GPU: single W7900, ~35% VRAM in use by generation server; disk 62G free;
  RAM healthy.

## 6. Related upstream work (duplicate check)

- No open PR or issue on sgl-project/sglang-omni mentions python-multipart
  (searched open PRs + issues). No pyproject variant on upstream main
  declares it (checked pyproject.toml, _rocm, _cpu, _npu, _xpu, _musa via
  API). The packaging gap is still unfixed upstream — standalone fix is not
  a duplicate. (Main pyproject does depend on gradio>=4.0.0, which can carry
  python-multipart transitively in SOME variants — exactly the reported gap.)
- No other ROCm PR exists against the author's repo or upstream for YuE2.

## Gates

- SOURCE_OF_TRUTH_PASS: every PR state and SHA above re-verified against
  GitHub this session (API + ls-remote), independent subagent check below.

## Independent verification (subagent)

Subagent re-queried GitHub directly for all three PRs, the fork branch, and
the evidence repo refs; all SHAs and states matched this document (see
`phase1_verification.md`).

## Independent verification result (2026-10-13 ~12:50Z)

All 7 checks MATCH (PR #1, fork branch, #2540, #42106, evidence refs, author
branch tip, no-new-ROCm-PRs search). One detail surfaced: sgl-project PR #2540
is cross-repository (head lives on the author's fork, isCrossRepository=true)
— conclusions unchanged. Final: **SOURCE_OF_TRUTH_PASS**.
