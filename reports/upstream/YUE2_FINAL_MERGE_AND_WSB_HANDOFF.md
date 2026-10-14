# YuE2 Final Merge & WSB Handoff — Consolidated Report

Session: 2026-10-13 (continuation) · Author: opencode acting for AIwork4me
Evidence repo: AIwork4me/YuE2-SGLang-ROCm · Working branch:
`handoff/omni-add_yue2-rocm-pr` (remote verified at each push; final SHA in
§GitHub delivery).

---

## 1. Our PR #1 (yiakwy-xpu-ml-framework-team/sglang-omni#1)

- OPEN, Ready-for-Review (not draft), MERGEABLE, head
  `fix/yue2-rocm-reference` @ 50c91c0888312ae784d3c42d9536665aa517dd9d,
  base `add_yue2` @ 85ae4b73 (unchanged).
- Single H800-request comment standing (2026-10-13T11:38Z); no author reply
  yet; no duplicate posted.
- Body corrected this session (documentation-only; code patch untouched):
  the unreliable `git fetch origin add_yue2 fix/yue2-rocm-reference` line
  replaced with the cross-repo-safe sequence (fetch author base from origin,
  fetch patch from AIwork4me fork by URL, pin PATCH_SHA, detached worktree,
  cherry-pick). Commands validated in a disposable local Git test repo
  including the already-integrated (empty cherry-pick) case.
- Gate: H800_HANDOFF_VALIDATED (instructions); H800 real run PENDING author.

## 2. Author HEAD & integration status

- Author `add_yue2` @ 85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9 — NO new
  commits; no review, no cherry-pick, no merge, no equivalent ROCm change
  detected (Phase-1 independent verification: SOURCE_OF_TRUTH_PASS).

## 3. H800 verification status

- Not performed by us (no H800 hardware); must not be claimed as PASS.
- Corrected instructions live on the PR #1 body + evidence repo
  `reports/merge_closure/H800_HANDOFF_CORRECTED.md`.

## 4. Official Omni PR #2540

- sgl-project/sglang-omni#2540 OPEN (cross-repository head on the author's
  fork), unchanged since 2026-10-05; not merged; no comments. ROCm support
  still rides PR #1 → author integration → #2540.

## 5. Original SGLang PR #42106

- sgl-project/sglang#42106 OPEN, CONFLICTING with main, head ced0ef7d
  (frozen sglang_commit of our WSB run), no movement since 2026-10-04.
- Minimal handoff prepared (`reports/merge_closure/SGLANG_42106_HANDOFF.md`):
  3 + 1 tiny capability-keyed guards (is_deepselect_supported()) mapped
  file:line to the author's four hot paths; quantization/kvcache fixes
  routed to independent main PRs, not bundled. No public contribution opened
  without agreement. Gate: SGLANG_42106_HANDOFF_READY.

## 6. Standalone python-multipart packaging fix

- Upstream still unfixed (no variant declares it; cpu/npu/xpu lack even the
  transitive gradio path).
- Ready branch `AIwork4me/sglang-omni:fix/declare-python-multipart` @
  **a5b78d7948fe11b388b22a2cb6609f76e39de510**, parented on upstream main
  tip cba5a74f: 6 pyprojects +1/-0 + 52-line regression test; 6/7 blob SHAs
  byte-identical to the previously reviewed commit daf1a113.
- Reproduced on isolated fastapi 0.143.0/starlette 1.8.0 (fails without,
  passes with 0.0.32). Floor >=0.0.20 validated (excludes CVE-2024-24762 /
  CVE-2024-53981-affected versions).
- Independent review: PACKAGING_FIX_REVIEWED (7/7 PASS, no YuE2
  contamination, no upstream collision).
- **NOT PUBLISHED — pending owner approval of final scope/description.**
  Draft: `reports/upstream/session-20261013/PYTHON_MULTIPART_PR_DRAFT.md`.

## 7. Scoring shutdown safety (P0) — FIXED & DEPLOYED

- v1 script's broad `pkill -f "sglang serve"` + unconditional
  `PIPELINE COMPLETE` replaced by `run_wsb_scoring_v2.sh` +
  `server_identity.py` + `push_verify.sh` + `scoring_stage_check.py`
  (evidence-repo @ c25b480, operational copies byte-identical; v1 retired on
  disk as `run_wsb_scoring.sh.v1-retired-unsafe-pkill`).
- Run-owned server identity receipt for the LIVE server captured without
  restart/signal: pid 487670, uid 0, /proc starttime 918563136, argv sha256,
  unique owner of the 127.0.0.1:31000 listen socket, run_id attributed.
  Sidecar lives in `run-state/`, never in frozen WSB config.
- Stop protocol: numeric/liveness/non-zombie/UID/starttime/argv/socket
  verification, exactly-one-match requirement, port drain (no in-flight
  requests), SIGINT → recheck → SIGTERM only after re-verification, never
  SIGKILL, BLOCKED + actionable status on refusal, no scoring while GPU
  allocation is unsafe.
- State machine: WAITING_FOR_384 → STRICT_AUDIT_PASS →
  GENERATION_SERVER_STOPPED → PER_SONGBENCH_COMPLETE →
  MULAN_ALLMUSICCAPS_COMPLETE → EVIDENCE_LOCAL_COMMITTED →
  EVIDENCE_REMOTE_VERIFIED → PIPELINE_COMPLETE; push failures yield
  LOCAL_COMPLETE_REMOTE_PENDING; PIPELINE_COMPLETE requires a verified
  matching remote SHA.
- 30 tests (mocked /proc trees; PID reuse, zombie, wrong UID/model/port,
  ambiguity, stop-failure, push-failure, idempotency); real signals only to
  self-spawned sleepers.
- 3 independent subagent reviews + delta re-verification: every P1 fixed
  (v1-alive guard exit 9; snapshot/git-add fatality; completeness-gated
  resume skips that a per-only crash remnant cannot bypass). Test-hook env
  overrides proven inert against the real /proc.

## 8. Scheduler deployment verification

- Old v1 scheduler (PID 494132) stopped via exact-PID SIGTERM from its
  verified stage-1 wait loop; receipts preserved
  (`run-state/scheduler-handoff-receipt.json`).
- Exactly ONE v2 scheduler alive; lock pid-verified; state WAITING_FOR_384
  bound to run_id wsbfull20261012T0041Z and the original run dir; contains
  no generation code (cannot regenerate candidates); liveness re-verified
  from an independent shell.
- Redundant queued GPU smoke watcher (PID 430873) safely retired pre-384 —
  it would have raced the scoring pipeline for the GPU at the 384 boundary
  (its evidence purpose was already fulfilled and published); receipt
  preserved.
- Generation driver (493545), server (487670), milestone watcher (494130)
  untouched and healthy throughout.

## 9-13. WSB run status (FINAL SECTION — see bottom for live results)

- Run: wsbfull20261012T0041Z, 192 prompts x 2 candidates, frozen seeds,
  model m-a-p/YuE2-3B@1a96eca, dataset e361b85a, config full (ode 32 /
  semantic 9000 / abc 4096 / vae_core 1024).
- Historical skipped(disk)/finalize_failed/quarantined events re-generated;
  only unique complete artifact identities count (60 skipped-disk events
  never counted).
- Strict pre-audit mid-run: 361 verified / 23 pending / 5 truncated-but-valid
  / 0 structural problems.
- Full strict audit + official scoring execute automatically via the v2
  pipeline at 384; results appended below when complete.

## 14. Independent reviewer verdicts

| Review | Scope | Verdict |
|---|---|---|
| GPU ops safety | v2 + identity tool + live setup | PASS (conditional P1 fixed & re-verified) |
| Shell reliability / failure injection | v2 + push_verify + identity tool | PASS (P1 fixed & re-verified; 21/21 tests) |
| WSB scoring integrity | official invocations, selection reuse, evidence | CONDITIONAL PASS → fixes verified (9/9 tests) |
| P1 delta re-verification | all three P1 fixes + hardening | P1_FIXES_VERIFIED: yes |
| Phase-1 source-of-truth | PR states/SHAs vs GitHub | SOURCE_OF_TRUTH_PASS (7/7) |
| Packaging fix isolation | upstream branch, diff, floor | PACKAGING_FIX_REVIEWED (7/7) |
| Final three-subagent audit (Phase 9) | end-state | see §FINAL AUDIT |

## 15. Remaining merge blockers

1. Author H800 validation of 50c91c08 (instructions delivered).
2. Author merge of PR #1 into add_yue2.
3. #42106 conflict resolution by the author (ROCm guards ready as follow-up).
4. Packaging PR publication (owner approval of scope/description).

## 16-17. Next exact actions

- Author: run the corrected H800 sequence on the PR #1 body; report commit
  SHA + environment; then merge PR #1.
- Upstream maintainer: none required beyond normal review of #2540 once the
  author's branch integrates dual-vendor support; python-multipart PR after
  owner approval.

## 18. Joint publicity timing

Only after ALL of: author H800 PASS, PR #1 integrated, #2540 merged upstream
(verified via upstream Git history). States kept distinct:
AMD_RUNTIME_VERIFIED (done) · CROSS_VENDOR_VERIFIED (pending H800) ·
AUTHOR_BRANCH_INTEGRATED (pending) · UPSTREAM_OMNI_MERGED (pending) ·
ORIGINAL_SGLANG_MERGED (pending) · PUBLIC_ANNOUNCEMENT_APPROVED (pending;
requires project + AMD stakeholder coordination).

---

## FINAL AUDIT + WSB RESULTS (2026-10-14T01:54:28Z PIPELINE_COMPLETE)

### W7900 WSB official results (run wsbfull20261012T0041Z)

- **Generation**: 384/384 unique candidates (192 prompts x 2), frozen seeds
  verified, natural driver exit at 14:54:17Z (2026-10-13).
- **Strict audit**: verdict FULL — 384 verified / 192 prompts / 0 problems /
  5 truncated-but-valid. Historical skipped(disk)x60, finalize_failed x2,
  quarantined x2 all re-generated; only unique complete identities counted.
- **PER (384-candidate arm)**: micro 0.22751 / macro 0.21810 (ASR
  Qwen3-ASR-1.7B on the frozen metrics env; 120 capped-ASR samples disclosed
  in summary).
- **SongBench (384 arm)**: 7 dimensions, 384 scored / 0 failed — Melody 6.670,
  Arrangement 6.952, Musicality 5.919, Vocal 7.128, Instrumental 7.028,
  Mixing 6.841, Structure 6.579.
- **Official PER best-of-2 selection (192)**: selected-arm PER micro 0.17010 /
  macro 0.16160 — selection strictly better than the unselected mean, as the
  protocol intends.
- **MuLan (192 selected)**: 192 scored / 0 failed.
- **AllMusicCaps (192 selected)**: 192 scored / 0 failed. The SAME official
  PER selection reused across metrics (additional/protocol.json
  reused_per_source: environment/per_song/protocol/receipt sha256 all match
  the scores side).
- **Performance baseline + GPU-vs-CPU-arm PER parity study**: completed
  (6-sample host-internal ASR arm comparison: 1 identical, 5 with
  transcription diffs — host-internal evidence only; no cross-vendor claim).
- **Evidence delivery**: validation/gfx1100-rocm7141 @
  **9e489c6c1e94f154b0a75426c1893858b62b9e55** (scoring snapshot commit,
  remote-verified by the pipeline AND independently);
  handoff/omni-add_yue2-rocm-pr @ e1037a95 (contains everything).
  Snapshot is valid JSON (≤400KB, graded per_song rows; full per_song.jsonl
  integrity anchored by recorded sha256).

### Gate

**W7900_WSB_FULL_AND_SCORED: ACHIEVED** (AMD_RUNTIME_VERIFIED;
CROSS_VENDOR_VERIFIED still pending author H800).

### Execution ledger (accurate)

Three pipeline aborts occurred, each safe (no false completion, no GPU work
while unsafe) and each fixed with a committed, reviewed-then-redeployed patch:

1. 00:07Z — stage-6 `reuse_per` frozen-lock mismatch: ROCm torch-family
   substitution not recognized. Fix: evaluator patch 0009 (mirrors
   verify_environment's WSB_ROCM_TORCH_OVERRIDE semantics; upstream path
   unchanged; disclosed in release.json) — commit 2ad0392.
2. 00:24Z — zombie server PID refused by identity tool (correct refusal);
   v2 pre-check misclassified zombie as "needs stopping". Fix: zombie =
   already-stopped semantics — commit b99b2b2.
3. 01:47Z — stage-8 branch guard blocked on an uncommitted tracked change
   (my process error) plus snapshot-truncation defect inherited from v1
   ([:200000] could emit invalid JSON). Fix: commit discipline + graded-row
   snapshot + stage-7 idempotent skip + untracked-tolerant dirty check —
   commit 4060dad.

### Phase 9 final three-subagent audit

| Auditor | Verdict | Notes |
|---|---|---|
| A — GPU ops & scoring safety | **PASS** | GPU idle, only non-reaped zombies; single verified SIGINT stop; no pkill ever; no duplicate scoring (exactly one 'Starting' line per metric); all aborts safe |
| B — Upstream code & CUDA compat | **PASS 6/6** | PR #1 clean 5-file patch +30/-6, corrected H800 body verified live; packaging branch intact & unpublished (needs rebase: upstream main moved cba5a74f→2cfb3b67); no H800 overclaim anywhere |
| C — Evidence & release integrity | **PASS 7/7** | Remote SHAs verified; snapshot valid & complete; metric provenance chain (protocol hashes, reused PER selection, rocm_torch_override disclosure) fully consistent; no cross-vendor overclaim; attribution sound |

P2 disclosures (non-blocking): earlier session commits carry a local test
git identity (`test <test@local`>) — hygiene only, corrected for future
commits; history NOT rewritten (no force-push). Snapshot embeds graded
per_song rows under the size cap with full-file sha256 anchors.

### 15-18 (final)

Merge blockers unchanged: author H800 run → PR #1 merge → #2540 ride-along;
#42106 author conflict resolution (guards ready); packaging PR publication
awaiting owner approval (rebase onto new main first). Joint publicity only
after AUTHOR_BRANCH_INTEGRATED + UPSTREAM_OMNI_MERGED are each verified in
upstream Git history, with project+AMD coordination.

