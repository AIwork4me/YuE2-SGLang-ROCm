# Final independent reviews — merge-readiness package (2026-10-16)

Three genuine independent subagent reviews were executed against the live
artifacts (worktrees, diffs, GitHub API, evidence files). Full reports are
reproduced verbatim below. Post-review corrections applied to the package
(see "Resolution log"): W7900→W7900D label harmonization, BS=1 peak VRAM
41.01→41.02 GiB per the governing erratum, `run-mac-ci` added to the label
enumeration, review-count phrasing fixed (4 PASS + 1 PASS-with-notes),
report 06 updated with the published lint-branch SHA.

## Verdicts

| Reviewer | Scope | Verdict | P0/P1/P2 | Notes |
|---|---|---|---|---|
| A | CUDA + ROCm software regression | **PASS** | 0 | 8×P3, none actionable; no model-math change, no CUDA regression, gates-only ROCm path |
| B | Upstream CI and Git | **PASS** | 0 | 10/10 claims verified; 3 info-level notes |
| C | Evidence and maintainer acceptance | **PASS** | 0 | 34/34 numeric claims traced; 5 minor findings, all resolved below |

Zero unresolved P0/P1 findings — publication gate met.

## Resolution log

- C1/C2/C5: applied (W7900D, 41.02 GiB, review-count phrasing).
- C3 (`1a9f2d92` corroboration): verified independently during publication —
  compare API shows the branch tip with parent `ced0ef7d` and 29 files;
  SHA is now recorded in report 06 as well.
- C4 (PR staleness risk): accepted — documents carry dual integration
  paths (PR merge or cherry-pick from pinned SHAs + patch files).
- B-F1 (workflow filename): the report text did not assert a filename;
  no change needed. B-F2 (`run-mac-ci`): label list corrected. B-F3:
  presentation-only.
- A: no action required (NOT TESTED items are explicitly deferred on-device
  checks that match the mission's H800 handoff design).

---

## Reviewer A — CUDA + ROCm software regression (verbatim)

# Reviewer A — Independent CUDA/ROCm Regression Audit (Final)

Date: 2026-10-16 · Scope: omni integration preview (PR1+PR2+style), sglang lint fix, sglang registry conflict artifact.
Method: read-only inspection of git objects + AST-level semantic differ (docstrings stripped, string-literal trailing-WS normalized) + token scans + py_compile. **No file modified, no test environment modified.**

## Overall verdict: **PASS** (for the CUDA+ROCm regression concern as a whole)

Independent code-level verification confirms: no model-output mathematics change, no CUDA fast-path regression, and the ROCm path is a capability gate routing to pre-existing fallbacks — not a kernel substitution. Caveats: GPU execution and the 62-test suite were NOT independently re-run (no torch/sglang env in this sandbox) — see NOT TESTED items. These do not block: every audited delta is either additive platform gating, formatting (AST-verified), or comment/config text.

## Verification performed (evidence)

1. **Topology/identity** — `/tmp/opencode/omni-integration-preview` HEAD = `ae11c6ad246023494a4f55f89e852384e019f5b4`; `075f1c62` parents = `85ae4b73 eca7770f`; `19efab35` parents = `075f1c62 4c089d19`; merge-bases of both PR heads vs base = `85ae4b73...`; worktree clean. Tree-level identity: `git diff eca7770f 19efab35 -- <PR1 files>` empty; same for PR2 (`4c089d19`) — matches report §2.
2. **PR delta** (`85ae4b73..19efab35`, 8 files +428/−6) — every source hunk inspected (below). All new `def`/`class` statements live in test files only (`FakePlatform`, `StubSynthesizer`, 12+13 tests).
3. **Style layer** (`19efab35..ae11c6ad`, 22 files +2262/−798) — full AST comparison: 15 files byte-equivalent modulo docstrings/trailing-WS; 7 files differ **only** by import-statement reordering with identical symbol sets (details below). Exactly 1 mode change (`examples/run_yue2_generate.py` 644→755) and exactly 8 `+…# noqa` lines — matches report §1 claim.
4. **sglang lint diff** (`0472797..50a70ad`, 28 .py + `.codespellrc`) — `.codespellrc` appends `,MoT,mot`; `suport`→`support`, `evalate`→`evaluate` in **comments only**; `python/sglang/multimodal_gen/runtime/pipelines/yue2_pipeline.py` **untouched** (0 diff lines) with the string key `"mot": runtime.model` intact at line 45. AST comparison: 18 files CLEAN; 10 files differ only by import reorders / annotation de-quoting / redundant-import removal (all hand-inspected, all benign). `python3 -m py_compile` OK on 11 sampled files incl. sampling.py, song.py, fastpath.py, fa3.py, deep_select.py, cuda_graph.py, modeling_yue2.py.
5. **Conflict artifact** — `patches/sglang_registry_conflict_resolved.py`: py_compile OK; preserves upstream `"fastvideo/fastvideo-fasth3-8-step-v2": "FastH3Pipeline"` (L188) **and** author's `"m-a-p/yue2-3b": "YuE2Pipeline"` (L187).
6. **Token sweeps** — searched both deltas for `flash_attn_2|fa2|topk|multinomial|softmax|temperature|top_p|top_k|repetition_penalty|scaled_dot_product|manual_seed|randn`: every hit is either a comment, a test, or an AST-verified identical rewrap of pre-existing expressions.

## Explicit answers

- **Does any audited delta change model output mathematics?** **No.** The PR delta touches no arithmetic: fa3/fastpath/song add `not current_platform.is_rocm()` conjuncts and one early-return; stages.py widens a device admission check and changes a *default batch size* on ROCm only; config.py adds an input-length cap (`max_speech_input_chars=None`, consumed by the pre-existing, unchanged validator in `sglang_omni/serve/speech_service.py:141-191,305`). Style + lint layers are AST-verified formatting/import-reorder only.
- **Does any delta regress the CUDA fast paths?** **No.** On CUDA `is_rocm()` is False: fa3 loads the shared varlen FA op under the same `SGLANG_YUE2_FA3=1` condition; fastpath still calls `_load_topk_backend()` then `torch.cuda.is_available()`; song still selects `_generate_song_tokens_step_graph`; stages short-circuits `is_cuda() or …` with the "4" default and env override intact. Tests `test_cuda_varlen_dispatch_unchanged`, `test_cuda_fast_sampler_unchanged`, `test_cuda_step_graph_selected`, `test_cuda_platform_accepted` encode exactly this (mocked platform).
- **Is the ROCm path a capability gate rather than a kernel substitution?** **Yes.** ROCm never swaps a kernel inside a dispatcher: it flips pre-existing selection branches to their already-shipped alternatives (fa3 → the base `torch.ops.aten._flash_attention_forward` fallback; sampler → reference sampler via `fast_sampler_available()→False`; step-graph → `_generate_song_tokens_looped`; batch default → 1). No FA2 is wired in anywhere (fa3 docstring explicitly defers that); no new TopK implementation exists in any delta.

## Findings

| # | Pri | Evidence | Root cause / detail | Recommended correction | Retest verdict |
|---|-----|----------|---------------------|------------------------|----------------|
| F1 | P3 | omni `sglang_omni/models/yue2/stages.py:43-60` (diff hunk `85ae4b73..19efab35`) | ROCm default `SGLANG_YUE2_BATCH_MAX_SIZE` becomes "1" — deliberate throughput clamp until batched AR/NAR is ROCm-validated; NVIDIA default "4" unchanged; env override honored | None (documented; revisit when ROCm batching validated) | PASS (env-override test `test_rocm_batch_size_env_override_still_honored` present) |
| F2 | P3 | omni `song.py` style hunk (`19efab35..ae11c6ad`): module body 15→13 statements | Style layer merges two `.fastpath` imports and drops the duplicate `from .protocol import ABC_END, MUSIC_END` (symbols already imported in the fuller protocol import). Symbol set before/after identical — verified; no circular-import risk (fastpath does not import song) | None | PASS (AST + py_compile + claimed suite green) |
| F3 | P3 | omni `sampling.py:158-159` (style) and sglang `python/sglang/srt/models/yue2/sampling.py:128-129` (lint) | Lazy in-function import order swapped (`modeling_yue2`↔`fastpath`). Both are pure module loads already deferred inside functions; order swap cannot change behavior absent import-time side effects, which neither has | None (note only) | PASS |
| F4 | P3 | sglang lint `python/sglang/kernels/ops/deep_select.py` hunk | Only real content: isort pulls `make_cpp_args` into a separate import line from the same module + trailing-WS fix at former L250. No constant, kernel, or math change (AST diffs at L21-24 were positional cascades from the inserted import) | None | PASS (py_compile OK; AST-verified) |
| F5 | P3 | sglang lint `request.py:29`, `yue2_loader.py:31` | Return annotation de-quoting `-> "Yue2Request"` → `-> Yue2Request`. Both classes are defined in-module before use; annotation is not evaluated at runtime in these paths | None | PASS |
| F6 | P3 | sglang lint `test_server_yue2.py:45-48` | Redundant `import sglang` inside `try` removed by isort; the subsequent `from sglang.multimodal_gen.registry import …` still initializes the package. Only non-formatting (but behavior-neutral) edit in the lint delta beyond reorders | None | PASS |
| F7 | P3 | omni `stages.py:48` | Error message changed to "YuE2 requires a CUDA or ROCm backend"; repo-wide grep shows no code/test asserts the old string | None | PASS |
| F8 | P3 | omni `fa3.py:29-50` | One-shot `_LOADED` cache snapshots platform detection at first `_load_varlen()` call — pre-existing semantics the ROCm gate inherits; cannot flip dispatch mid-process | None (pre-existing) | PASS |

No P0/P1/P2 findings.

## NOT TESTED (with reason)

- **Unit suite re-run** — report claims 62/62 under `env-omni-rocm` (torch 2.12.0+rocm7.14.1); no torch/sglang environment exists in this audit sandbox. Counts are internally consistent (12 platform-gate + 13 speech-cap + 37 model-capabilities = 62; `def test_` counts verified: 12 and 13).
- **On-device execution** — H800 CUDA smoke and W7900 ROCm run not performed here; consistent with report §7 deferring the H800 check to report 05. The platform-gate tests are mocked-platform tests, not GPU proof.

## Conclusion

The evidence chain holds under independent inspection: the delivered PRs are gates-only, the style/lint layers are provably non-semantic at the AST level, and the conflict artifact is lossless. Remaining risk is confined to on-device behavior (report 05 scope), not to these deltas.

**Verdict: PASS.**


## Reviewer B — Upstream CI and Git (verbatim)

# Reviewer B — Independent Upstream CI & Git Integration Audit (Final)

- Date: 2026-10-16
- Auditor: Reviewer B (independent re-verification; read-only)
- Tooling: `gh` CLI (authenticated as AIwork4me, read-only API calls), local `git`, `diff`
- Scope: 10 claims from the just-completed analysis; no writes, pushes, or label changes performed. One temporary evidence-fetch file (`/tmp/opencode/m3/registry.main.fetched`) was created for hash verification and removed afterward.

## Overall verdict: PASS

All 10 claims verified against live GitHub API data and local artifacts. 3 minor (informational) findings — none invalidate any claim.

## Per-claim verification table

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| 1 | sgl-project/sglang-omni#2540 state & CI | TRUE | `pulls/2540`: head_sha `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9`, mergeable=true, mergeable_state=blocked, state=open, merged=false. `commits/{sha}/check-runs`: total_count=0. `actions/runs?head_sha=`: exactly 6 runs, all conclusion=action_required — Lint 37260615543, Docs Check 37260615542, Test Layout 37260615546, CPU CI 37260615550, Omni CI 37260615890, XPU CI 37260615544. requested_reviewers=[FrankLeeeee]. Reviews: 2, both `copilot-pull-request-reviewer[bot]` (COMMENTED). Issue comments: 0; review_comments: 0. |
| 2 | sgl-project/sglang#42106 state & CI | TRUE | `pulls/42106`: head `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`, mergeable=false, mergeable_state=dirty, labels=[documentation, diffusion, jit-kernel] (no run-ci), open/unmerged. check-runs at head: exactly 3 failures (pr-test-finish, pr-test-extra-finish, pr-test-amd-finish); every other check skipped. Run 37188915379 "Lint": conclusion=failure, job `lint` failed at step "Run pre-commit checks". Run 37188915580 (pr-test.yml, "PR #42106 - Add yue2"): job `call-gate / pr-gate` failed at step "Require run-ci label (optional)". |
| 3 | Author PRs open w/ expected heads & parent chains | TRUE | yiakwy…/sglang-omni#1: open/unmerged, head `eca7770f…44758a5f92444b75538`, author AIwork4me. #2: open/unmerged, head `4c089d193f1186aeb40609ac4913273db9cdea95`. AMD-sglang-benchmark-fork#1: open/unmerged, head `def437fb7949f26bd1b06473882fd928757c6377`. Parents: eca7770f → 50c91c0888312ae784d3c42d9536665aa517dd9d → 85ae4b73…; 4c089d19 → 4ad6658b468b4de6774389c2d7a91e52b25069ec → 85ae4b73…. |
| 4 | Handoff branches & commit chains | TRUE | AIwork4me/sglang `fix/yue2-upstream-lint` = `1a9f2d92a201b21242ca6c1bbe8a070189b0a913`, parent exactly `ced0ef7d…`. compare `ced0ef7d...fix/yue2-upstream-lint`: ahead_by=1, files=29, merge_base=ced0ef7d. AIwork4me/sglang-omni `preview/omni-yue2-integration-style` = `ae11c6ad246023494a4f55f89e852384e019f5b4`. Chain: ae11c6ad (style fixes) → parent 19efab35 ("preview-merge-2: integrate long-lyrics PR#2", parents 075f1c62 + 4c089d19) → 075f1c62 ("preview-merge-1: integrate ROCm reference-path PR#1", parents 85ae4b73 + eca7770f). Matches claimed geometry exactly. |
| 5 | Merge-base geometry & conflict candidates | TRUE | compare `main...ced0ef7d`: merge_base `ba68306256d64c53d302dc5d2f3be9e388af0738`, ahead_by=3 (behind_by=839). Sampled 9 of the 35 PR files via `commits?path=…&since=2026-10-04T08:22:36Z` (≥8 required): modeling_yue2.py=0, fastpath.py=0, fa3.py=0, song.py=0, yue2_pipeline.py=0, yue2_loader.py=0, deep_select.py=0, **registry.py=4**, **http_server.py=3**. registry.py and http_server.py are the only ones >0, exactly as claimed. |
| 6 | Local 3-way merge evidence (/tmp/opencode/m3/) | TRUE | `grep -c '^<<<<<<<'`: registry.merged=1 (exactly one conflict hunk), http_server.merged=0. `diff registry.main registry.resolved`: single hunk `186a187 > "m-a-p/yue2-3b": "YuE2Pipeline",` — no other changes. Authenticity: fetched main's registry.py via contents API; `git hash-object` = `d60894623833e8d60e0a998448376a5ec0a977f3` for both fetched copy and local registry.main (identical). |
| 7 | Author branches unmodified | TRUE | yiakwy…/sglang-omni `add_yue2` = `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9`. AMD-sglang-benchmark-fork `add_yue2` = `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`. Both unchanged. |
| 8 | No duplicate PRs | TRUE | `gh pr list` yiakwy…/sglang-omni (all): exactly #1 (OPEN, AIwork4me, "…ROCm reference path…") and #2 (OPEN, AIwork4me, "…full-song lyrics…"). AMD-sglang-benchmark-fork: exactly #1 (OPEN, AIwork4me). AIwork4me/YuE2-SGLang-ROCm (all): exactly 3 — #1 CLOSED, #2 CLOSED, #3 MERGED; no new PRs. |
| 9 | Workflow-permission claims | TRUE (minor naming/enumeration notes) | `.github/CI_PERMISSIONS.json` exists on sgl-project/sglang-omni main (7 allowlisted users with can_tag_run_ci_label/can_rerun_failed_ci). Slash-command workflow exists at `.github/workflows/slash-command-handler.yml` (dashes; claim wrote `slash_command_handler.yml`) and its `slash_command` filter recognizes exactly `/tag-run-ci-label`, `/rerun-failed-ci`, `/tag-and-rerun-ci`. `.github/scripts/resolve_ci_labels.py` defines run-asr-ci, run-tts-ci, run-mps-ci, run-omni-ci, run-intel-cpu-ci, run-intel-xpu-ci + RUN_ALL_LABEL "run-all-ci" — `grep -ci yue2` = 0 (no yue2 label). See F2: it also defines run-mac-ci, not listed in the claim. |
| 10 | Omni branch ruleset | TRUE (response is an array, values confirmed) | `rules/branches/main` returns an array of rules. `required_status_checks` rule has exactly one context: `lint` (integration_id 15368). `pull_request` rule parameters: required_approving_review_count=1, require_extra_approval_for_unattributed_changes=true (also: squash-only merge). |

## Findings

### F1 — Slash-command workflow filename discrepancy
- Priority: Informational (no impact)
- Evidence: Claim cites `slash_command_handler.yml`; actual path is `.github/workflows/slash-command-handler.yml` (also `scripts/ci/utils/slash_command_handler.py` exists for the Python helper).
- Root cause: Underscore/dash transcription in the analysis notes.
- Recommended correction: Note exact filename `slash-command-handler.yml` in future citations; command set itself verified exactly as claimed.
- Retest verdict: PASS (content claims fully verified).

### F2 — resolve_ci_labels.py stage-label enumeration non-exhaustive
- Priority: Low (does not affect any conclusion)
- Evidence: `grep -oE 'label="run-[a-z-]+"'` yields 7 stage labels including `run-mac-ci` (line 93), which the claim omitted; claim listed only run-asr/tts/mps/omni/intel-cpu/intel-xpu + run-all-ci.
- Root cause: Enumeration in the analysis stopped one label short.
- Recommended correction: Include `run-mac-ci` in any future inventory of stage labels. Crucially, "NO yue2 label" remains true (0 occurrences of yue2).
- Retest verdict: PASS (all asserted labels exist; no yue2 label; omission only).

### F3 — Ruleset response shape differs from claim's implied single object
- Priority: Informational
- Evidence: `gh api repos/sgl-project/sglang-omni/rules/branches/main` returns an array of 7 rules (deletion, non_fast_forward, creation, required_linear_history, pull_request, copilot_code_review, required_status_checks); jq paths like `.parameters.required_status_checks` on the top-level object fail.
- Root cause: Claim described the two relevant rules, not the full payload shape.
- Recommended correction: When scripting, index the array (e.g., `.[] | select(.type=="required_status_checks")`). The asserted values (exactly "lint"; approving_review_count 1; extra approval for unattributed changes true) are all confirmed.
- Retest verdict: PASS.

## Summary
10/10 claims verified TRUE against live API + local evidence. The upstream state (omni #2540 blocked on action_required workflows with FrankLeeeee review pending; sglang #42106 dirty-conflicted with finish-gate failures from missing run-ci label + lint failure), handoff branch geometry, merge-conflict RCA (registry.py the sole conflicted file), author-branch immutability, absence of duplicate PRs, and permission-model claims all reproduce exactly. No modifications were made to any repository, PR, branch, or label during this audit.

**Overall: PASS**


## Reviewer C — Evidence and maintainer acceptance (verbatim)

# Reviewer C — Independent Evidence & Maintainer-Acceptance Audit (Final)

Date: 2026-10-16 · Mode: read-only (nothing modified) · Scope: five merge-readiness documents audited against the four source evidence files, with secondary verification against the wider evidence repo (reports 01–08, reviews/omni_wsb/VERDICTS.md, final_acceptance/PHASE0_BASELINE.md).

**Evidence keys:** WSB = `reports/author_acceptance/OMNI_WILDSOGNBENCH_GFX1100.md` · BS1 = `reports/author_acceptance/OMNI_BS1_CONCURRENCY_GFX1100.md` · CLO = `reports/final_acceptance/EVIDENCE_INTEGRITY_CLOSURE.md` · SPC = `reports/final_acceptance/SERVING_PERFORMANCE_CORRECTION.md`

**Documents audited:** 02_OMNI_2540_PR_DESCRIPTION_DRAFT.md, 02_OMNI_2540_ONE_PAGE_MAINTAINER_SUMMARY.md, 09_OMNI_MERGE_HANDOFF.md, 10_SGLANG_MERGE_HANDOFF.md, AUTHOR_MESSAGE_FOR_REVIEW.md (all in `reports/merge_readiness/`).

---

## Overall verdict: **PASS**

No numeric mismatch with the evidence files. No integrity violation (no fabricated results, no CI-passed claim, no H800-validation claim, no cross-vendor speedup ratio, no quality/throughput conflation). Five minor P3 documentation/traceability notes below — none blocks the handoff; all are one-line corrections or pre-posting verifications.

---

## 1. Numeric traceability table

Legend: MATCH = exact/rounding-consistent with evidence. (sec) = verified against a secondary file inside the same evidence repo (noted). EXT = external source (GitHub PR), explicitly attributed in the doc — accepted as attributed, not evidence-verifiable.

| # | Claim (doc:line) | Source (file:line) | Verdict |
|---|---|---|---|
| 1 | SongBench GA full-384 **6.7301** (02:104, 02b:35, 09:33) | CLO:105 ("GA FULL = 6.7301"); WSB:25 (6.730) | MATCH |
| 2 | SongBench GA selected-192 **6.7323** (02:105, 02b:35, 09:33) | CLO:105 ("SELECTED = 6.7323"); WSB:28 (6.732) | MATCH |
| 3 | PER full-384 micro **0.24819** (02:106, 02b:36, 09:34) | WSB:16, WSB:86; CLO:103 (recomputed 0.24819) | MATCH |
| 4 | PER selected-192 micro **0.17608** (02:107, 02b:36, 09:34) | WSB:26, WSB:86; CLO:104 (recomputed 0.17608) | MATCH |
| 5 | MuLan ≈ **0.5080** (02:108, 02b:36, 09:34) | WSB:29 (0.50803); CLO:109 | MATCH |
| 6 | AllMusicCaps ≈ **0.4059** (02:109, 02b:36, 09:34) | WSB:30 (0.40595); CLO:109 | MATCH |
| 7 | Q3O **not tested** (02:110, 02b:48, 09:35) | WSB:31, WSB:133–136 | MATCH |
| 8 | Arm-A GA **6.731** (02:113, 09:41, 10:18) | WSB:25 (col A) | MATCH |
| 9 | Every SongBench dimension within **±0.002** (02:114, 02b:37–38, 09:41–42) | WSB:18–25 — recomputed: max \|Δ\| = 0.002 (Melody 6.670/6.668, Musicality 5.919/5.917) | MATCH |
| 10 | MuLan/AMC within 0.002 (02:114) | WSB:29,30 — Δ(MuLan)=0.0019, Δ(AMC)=0.0008; WSB:39 states 0.002/0.0008 | MATCH |
| 11 | **384/384**, strict audit FULL, 0 structural problems (02:96–97, 02b:33, 09:32) | WSB:3, WSB:63–66; CLO:40 | MATCH |
| 12 | ASR cap **128/384** unselected, **512 capped repeats**, included-not-excluded (02:122–123, 02b:47) | WSB:92–94 | MATCH |
| 13 | 5 truncated-but-valid retained, no cherry-picking (02:126) | WSB:69–71, WSB:139 | MATCH |
| 14 | Author reference PER **8.44%** (02:121, 02b:48) | WSB:26 (0.0844) | MATCH |
| 15 | BS=1 **P50 217.3 s / mean 218.7 s / audio 223.0 s**, n=24, 0 errors (02:139–140, 02b:39, 09:37) | BS1:48–53; SPC:59–60 (217.251/218.725/223.031) | MATCH |
| 16 | Real-time generation speed **1.030×** (02:141, 02b:40, 09:38) | BS1:55 (1.030×); SPC:54 (1.0296) | MATCH |
| 17 | Client E2E RTF **0.975** (02:142, 02b:40, 09:38) | BS1:56 (0.975); SPC:55 (0.9749) | MATCH |
| 18 | Throughput ≈ **0.0046 req/s** (02:143, 02b:40, 09:38) | BS1:75–78 (RPS 0.0046 all C); SPC:57 | MATCH |
| 19 | Peak VRAM **44.04 GB (41.01 GiB)** (02:144) | BS1:57 (41.01 GiB); SPC:103 says **41.02 GiB** | MATCH vs BS1; see Finding 2 (0.01 GiB rounding split inside evidence itself) |
| 20 | Sweep C=1..8: 24/24, **0 errors**, RPS constant 0.0046, P50 **216.7→449.5→896.0→1736.0** linear (02:146–147, 02b:41, 09:39) | BS1:75–78, 84–86; SPC:66–69 (216.748/449.530/896.004/1736.032; C8/C1=8.01×) | MATCH |
| 21 | GPU batch = 1 via `SGLANG_YUE2_BATCH_MAX_SIZE=1`; client C ≠ GPU batch (02:148–151) | BS1:18, 84–96 | MATCH |
| 22 | Arm-A PER **0.1701** selected / **0.2275** unselected micro; MuLan **0.5099**; AMC **0.4052**; GA 6.731 (10:18) | WSB:16 (0.22751), 26 (0.17010), 29 (0.50993), 30 (0.40519), 25 (6.731) | MATCH |
| 23 | Author H800 statements "**7.0 s** BS=1 full_song / **1.81 req/s**" quoted as author statements (02:59–61, 02b:17, 10:16) | BS1:100–101 (author statements, flagged incomparable) | MATCH (correctly attributed, never adopted as our measurement) |
| 24 | H800 ≠ comparable workload; metadata requested; **no speedup ratio** (02:193–202, 02b:60–62) | BS1:98–107 | MATCH |
| 25 | Pilot duration parity, 20 candidates (02:115–116) | WSB:158–159; reviews/omni_wsb/VERDICTS.md:6 (Δ 0.00 s) | MATCH |
| 26 | PR#1 head **eca7770f** (02:14, 09:25) | final_acceptance/PHASE0_BASELINE.md:32–37: eca7770f = 50c91c08 + comment-only update; run_config pins behavioral fix 50c91c08 | CONSISTENT (see Resolution Note) |
| 27 | 62/62 unit tests (AUTHOR_MESSAGE:16) | 04_AUTHOR_OMNI_INTEGRATION_PREVIEW.md:51 | MATCH (sec) |
| 28 | 12/12 platform-gate tests (02:162) | 04:48; WSB §5 ("unit gates 12/12 pass") | MATCH (sec) |
| 29 | Six Omni workflows `action_required`, no CI executed (02:224–225, 02b:4–5, 09:48–49) | 01_LIVE_PR_AND_CI_MATRIX.md:27–41 | MATCH (sec) |
| 30 | SGLang lint run 37188915379, 6 hooks, patch 28 files + 1-line .codespellrc (10:26–33) | 01:73; 06:5–7, 76–77, 101 | MATCH (sec) |
| 31 | Single registry.py conflict hunk; http_server.py auto-merges (10:34–39) | 07:25–26 | MATCH (sec) |
| 32 | benchmark-fork#1 `def437fb` (10:49) | 01:118 | MATCH (sec) |
| 33 | e0683229 validation: GA **6.7146** vs native **6.7360**, PER **8.15% vs 8.61%** (02:130–133, 02b:19–20, 10:17) | 01:93 (YuE2 original author's PR comment) | MATCH (sec, external PR comment — correctly attributed) |
| 34 | Author PR body: GA 6.721 vs paper 6.730, PER 8.29% vs 8.44% (10:16) | Not in evidence repo; labeled "(PR body)" | EXT — attributed, unverifiable here (8.44% consistent with WSB:26) |
| 35 | `1a9f2d92` = fix/yue2-upstream-lint head (10:32,47; AUTHOR_MESSAGE:22) | **Not found anywhere else in the evidence repo** (06 cites branch + patch + local scratch `50a70ad`) | MISMATCH (traceability gap) — Finding 3 |

**Resolution Note (item 26):** The WSB evidence says "PR#1 head 50c91c08" while the merge docs say "PR#1 head eca7770f". This is NOT a discrepancy: per PHASE0_BASELINE.md:37 and report 04:14, `eca7770f` is the pushed comment-only review update whose parent is the behavioral fix `50c91c08` (what run_config pins as `pr1_head`). The merge docs correctly cite the current PR head; the W7900 validation ran on exactly that content plus disclosed bench-only instrumentation (`c4841f0c`). Resolved — no action.

---

## 2. Terminator discipline (audit item 2) — CLEAN

- **Client concurrency vs GPU batch:** every serving statement carries "GPU batch = 1" / `SGLANG_YUE2_BATCH_MAX_SIZE=1` (02:135,148–151; 09:37) and 02 states explicitly "Client concurrency is not GPU batch size" (02:150–151). Matches BS1:71–96 ("C=8 is NOT GPU batch 8").
- **E2E RTF vs GPU compute RTF:** all three docs that mention RTF label it "client E2E RTF (wall_s/audio_s)" (02:142, 02b:40, 09:38) and 02:153–155 explicitly separates it from GPU compute RTF. Matches BS1 erratum and SPC §1–3.
- **Real-time speed vs RTF:** "Real-time generation speed … 1.030×" uses the erratum's corrected label (BS1:55); 02:154–155's "speed multiplier is the reciprocal statement of per-request RTF" is correct per-request (avoids the Jensen-gap trap SPC:44–46 warns about for means).
- **SongBench quality vs throughput:** never conflated; 02:155–156 states the separation explicitly; no table mixes quality with throughput rows.
- Sweep C≥2 RTF >1 values are either omitted (good) or would be queue-wait-inclusive; no doc presents them as GPU-compute RTF or as a regression. No violations found.

## 3. Disclosures (audit item 3) — ALL PRESENT AND ACCURATE

| Disclosure | 02 draft | 02b summary | 09 | 10 | Evidence |
|---|---|---|---|---|---|
| Q3O not tested | :110, :187 | :48 | :35 | — | WSB:31, §6 |
| PER = ROCm adaptation, not author's NVIDIA evaluator; no exact parity | :119–121, :187–188 | :46–48 | :35–36 | :20–22 | WSB §4, §5.6 |
| ASR truncation/capping 128/384, included-not-excluded | :122–125 | :47 | :35–36 | — | WSB:92–101 |
| No exact cross-platform parity claim | :128 | (implied via PER caveat) | :36 | :22 | WSB:41–45, §5.6 |
| H800 7.0 s / 1.81 req/s = different incomparable workload; metadata requested; **no speedup ratio anywhere** | :193–202 | :60–62 | (not raised = fine) | — | BS1 §6 |
| 5 truncated-but-valid retained, no exclusions | :126 | — | — | — | WSB:69–71 |

Checked every table and sentence in all five docs: no counter-example found. The metadata-request list in 02:199–202 matches BS1:104–106 item-for-item.

## 4. Arm-A cross-check (audit item 4) — MATCH

Arm-A numbers cited in the docs (GA 6.731; PER 0.1701/0.2275; MuLan 0.5099; AMC 0.4052) reproduce WSB table column A exactly (WSB:16–30). The "every SongBench dimension within ±0.002" claim was independently recomputed from the WSB arm table: deltas are Melody 0.002, Arrangement 0.001, Musicality 0.002, Vocal 0.001, Instrumental 0.001, Mixing 0.001, Structure 0.000, GA 0.001 — max 0.002, consistent with WSB:39 and WSB:98 ("max delta 0.002").

## 5. Claim-to-source traceability of the PR draft (audit item 5) — PASS

- **Integration precondition:** present and unambiguous (02:11–18): the ROCm path "exists only after" PR#1 integration; at head `85ae4b73` the source is "CUDA-verified only"; the description "must not be posted as-is" otherwise, with the fallback ("section 4 reduced to 'planned'"). The author checklist repeats it (02:233–234).
- **Author statements preserved as quotes:** "BS=1, full_song generation 7.0s" and "MAX Conccurency, 1.81 reqs / sec" are quotation-marked and attributed (02:57–61), never adopted as verified measurements; the incomparability caveat follows (02:193–202).
- **No CI-passed claim:** 02:222–227 states "no CI has executed yet (no lint result exists)" and lists required next steps; "12/12 pass locally" (02:162) is correctly scoped to local unit tests. Consistent with 01:27–41.
- **No official-support claim:** the draft is framed as proposed text pending author adoption and maintainer approval; nothing asserts support status pre-merge.

## 6. H800 status honesty (audit item 6) — PASS

- 02:165–167: H800 smoke on the integrated commit is "still needed"; author's existing evidence covers `85ae4b73`/`ced0ef7d` only.
- 09:50: "No H800 run exists on any integrated commit."
- 10:60–62: "Same-commit dual-vendor verification does not exist until the author runs the H800 check."
- 02b:68–69 and AUTHOR_MESSAGE:25–27 request the run.
- Report 05 exists (`05_H800_ACCEPTANCE_CHECKLIST.md`) and is a checklist only: test plan + empty receipt template; explicitly "no fabricated hardware results included or implied" (05:100–101). No document claims an H800 result that does not exist.

## 7. Public/private separation (audit item 7) — PASS

- All evidence pointers in 02 (:8–9, :209–213), 02b (:76), 09 (:62–63) reference the public evidence repo branch `validation/gfx1100-rocm7141` only.
- AUTHOR_MESSAGE:41–42 points to the new handoff branch `handoff/yue2-upstream-merge-readiness` (distinct from the validation branch) — consistent with "handoff branch will be new".
- Fork PR SHAs (`eca7770f`, `4c089d19`, `ae11c6ad`, `def437fb`, `1a9f2d92`) are contribution-delivery metadata addressed to the author in the author's own fork PRs — appropriate, not private-evidence leakage. No document claims any of these PRs is merged; 02b:29 states "The author has not yet merged PR #1" and 01 §3 recorded all three OPEN/unmerged. (If #1/#2 have since been CLOSED rather than merged, see Finding 4.)
- Raw host paths (`/workspace/...`) stay inside evidence reports, not in the audited docs; the audited docs reference repo-relative evidence paths only.

## 8. Reviewer handoff quality (audit item 8) — PASS

- **09:** five ordered steps with named actors (author vs maintainer), exact full SHAs table, explicit "What is NOT yet true" section (anti-overclaim guard), concrete maintainer actions incl. ruleset nuance (`require_extra_approval_for_unattributed_changes`). Actionable.
- **10:** exact PR identity, three blockers each with root cause + prepared artifact + exact command, ordered author actions, separation guarantees. Actionable.
- **Language:** measured throughout; strongest phrasing ("strongest new upstream-acceptance signal", "strong signal") refers to a real, attributed third-party validation (report 01:93). No marketing inflation, no "production-ready"-class claims, no fake results detected in any of the five documents.

---

## Findings

### Finding 1 — P3 (Minor, documentation): GPU SKU inconsistency "W7900" vs "W7900D"
- **Evidence:** BS1:13 says "AMD Radeon Pro **W7900D** 48GB (gfx1100)"; WSB:4 says "AMD Radeon W7900 48GB"; all audited docs say "Radeon PRO W7900" (02:79,173; 02b:25; 09:30; 10:18).
- **Root cause:** the two evidence reports were authored with different SKU strings; the merge docs inherited the WSB variant.
- **Impact:** none on results (same gfx1100, 48 GB, same host), but an upstream PR should not carry an ambiguous SKU.
- **Recommended correction:** pick one SKU (verify the actual hardware; if W7900D, correct WSB:4 and the five docs; if W7900, correct BS1:13) before posting 02 upstream.
- **Retest verdict:** PASS after one-line SKU harmonization.

### Finding 2 — P3 (Minor, documentation): VRAM GiB rounding split (41.01 vs 41.02)
- **Evidence:** 02:144 and BS1:57 say 44.04 GB = 41.01 GiB; SPC:103 (the governing erratum) recomputes 44,043,042,816 B = **41.02 GiB** (41.0165 GiB rounds to 41.02).
- **Root cause:** 02 quotes the pre-erratum BS1 figure; the erratum corrected the rounding but 02 was not updated.
- **Recommended correction:** change 02:144 to "41.02 GiB" (or cite both and defer to SPC).
- **Retest verdict:** PASS after edit.

### Finding 3 — P3 (Minor, traceability): uncorroborated commit SHA `1a9f2d92`
- **Evidence:** 10:32, 10:47 and AUTHOR_MESSAGE:22 pin `AIwork4me/sglang@fix/yue2-upstream-lint` to `1a9f2d92` (parent `ced0ef7d`); no other file in the evidence repo contains this SHA — report 06 cites the branch, the patch file, and a local scratch commit `50a70ad` only.
- **Root cause:** the handoff docs cite the pushed branch tip; the backing RCA report predates or omits it.
- **Recommended correction:** before sending the author message, verify `git ls-remote https://github.com/AIwork4me/sglang.git fix/yue2-upstream-lint` equals `1a9f2d92…` and record it in report 06 (or drop the SHA and keep the cherry-pick-FETCH_HEAD instruction, which 06:86–87 already provides).
- **Retest verdict:** PASS after verification (the instruction remains executable even without the SHA).

### Finding 4 — P3 (Minor, staleness risk): "Author merges PR #1/#2" instructions depend on those PRs remaining open
- **Evidence:** 02:233–235, 09:5–7, AUTHOR_MESSAGE:15 instruct merging yiakwy…/sglang-omni#1 (`eca7770f`) and #2 (`4c089d19`); report 01:109–118 (2026-10-16 snapshot) recorded all three contribution PRs OPEN/unmerged. Handoff context indicates #1/#2 may since be CLOSED (not merged).
- **Root cause:** live-GitHub state drift after the docs were written.
- **Impact:** low — every instruction is dual-pathed (exact SHAs, `git fetch <url> <sha>` / patch files in `patches/`, report 04 §6 and 05 give both options), so the handoff remains executable if the PRs are closed; but "merge the PR" phrasing would be stale.
- **Recommended correction:** re-check PR states at send time; if closed, reword to "reopen or cherry-pick the pinned SHAs" (one sentence per doc). No document falsely claims merged status today.
- **Retest verdict:** PASS (verify-then-send).

### Finding 5 — P4 (Cosmetic): "five independent review PASSes" drops the with-notes qualifier
- **Evidence:** 02b:78; VERDICTS.md:3–11 = four PASS + one PASS-WITH-NOTES (3 P1 + 3 P2, all resolved); VERDICTS.md:11 itself summarizes "All five reviews PASS (with notes resolved)".
- **Root cause:** shorthand following VERDICTS.md's own bottom line.
- **Recommended correction (optional):** "five independent review PASSes (one with notes, all resolved)" in 02b.
- **Retest verdict:** PASS as-is; cosmetic.

---

## Explicitly checked and found clean (no findings)

1. All 34 traceable numeric claims match (table §1); the only traceability gap is the `1a9f2d92` SHA (Finding 3).
2. The `eca7770f` vs `50c91c08` PR#1-head difference is internally documented and resolved (PHASE0_BASELINE.md:37; report 04:14) — not a mismatch.
3. No conflation of client concurrency/GPU batch, E2E RTF/GPU-compute RTF, speed multiplier/RTF, or quality/throughput (§2).
4. All five required disclosures present and accurate (§3).
5. Arm-A cross-check numbers and the ±0.002 delta claim reproduce exactly from the WSB arm table (§4).
6. PR draft integration precondition, author-quote preservation, CI honesty, no pre-merge support claims (§5).
7. No H800-validation claim on any integrated commit; report 05 is checklist-only with an empty receipt template (§6).
8. Public-branch evidence pointers only; no private-branch leakage; no merged-status claims (§7).
9. Handoffs 09/10 actionable with exact SHAs, exact commands, named actors; no fabricated results; no marketing inflation (§8).
10. External claims (author PR-body 6.721/8.29%; third-party e0683229 validation) are explicitly attributed to their external sources; the latter is additionally mirrored in report 01:93.

**Final: PASS — approve the handoff documents for release, subject to the four P3 pre-send touches (SKU harmonization, 41.02 GiB, verify `1a9f2d92`, re-check PR open state).**
