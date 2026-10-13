# YUE2_ROCM_MINIMAL_MERGE_CLOSURE.md — 2026-10-13

Merge-closure report for the YuE2 ROCm minimal patch (mission: evidence → ready for review → author integration).

## 1. ROCm PR #1

- URL: https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1
- State at closure: **OPEN / READY FOR REVIEW** (Draft→Ready transitioned 2026-10-13, verified via API; `isDraft:false`)
- HEAD: `50c91c0888312ae784d3c42d9536665aa517dd9d` (branch `fix/yue2-rocm-reference`, AIwork4me fork — remote SHA verified identical)
- Base: author `add_yue2` @ `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` (unchanged since 2026-10-05; verified)
- mergeable: MERGEABLE (mergeStateStatus UNSTABLE solely because the fork has no CI checks configured)
- PR body updated 2026-10-13 with the verified W7900 HTTP E2E evidence (self-contained; no private-repo links; zero occurrences of the private repo name)
- Author handoff comment posted: issuecomment-6144689787 ("YuE2 ROCm E2E PASS — request H800 confirmation and add_yue2 integration")
- Files: 5 (+237/−6) — `sglang_omni/models/yue2/{stages,song,fastpath,fa3}.py` (+30/−6) + `tests/unit_test/models/test_yue2_platform_gates.py` (+207)

## 2. Real W7900 HTTP test results (verified; see evidence branch)

Environment: AMD Radeon PRO W7900D (gfx1100, 48 GB), ROCm 7.14.1 / HIP 7.14.60850, torch 2.12.0+rocm7.14.1, real `sgl-omni serve`, `POST /v1/audio/speech`, seed 831001, cot=full; pristine upstream SGLang checkout (empty diff); model `m-a-p/YuE2-3B@1a96eca`, VAE `YuE2-Vae-legacy@b54118f0`.

| Test | Verdict | Detail |
|---|---|---|
| SHORT | PASS | HTTP 200, audio/wav, 48,000 Hz stereo, 20.479 s, RMS 0.0860, SHA256 `358ffc66b6d899231dc75fc5c9bcef0b0f1840e2c2532dff4363357d2882feed` |
| FULL CONFIG | PASS | HTTP 200, audio/wav, 48,000 Hz stereo, 47.239 s, RMS 0.1470, SHA256 `218634d46abfe48f1aa27c3dd43d6d84e1776fc6c64e6c0dc772fd52330526bd` |

Full-config token limits were upper bounds — generation stopped at **natural EOS** (not a long-form endurance claim). GPU trace brackets the full-config window; smoke-window utilization is inferential (server.log synth elapsed 15.25 s). Both SHA256s independently recomputed from raw bodies this session and by independent Reviewer A/C.

## 3. Independent reviewer verdicts (2026-10-13)

| Review | Scope | Verdict |
|---|---|---|
| Phase 1 — upstream state | PR #1 / #2540 / #42106 reconciliation | BLOCKED-as-found (draft, unreviewed) → blockers resolved this session; report `reports/upstream/CURRENT_UPSTREAM_STATE.md` |
| Phase 2 — evidence reconciliation | Numbers vs raw artifacts | PASS (zero numeric mismatches; 2 cosmetic corrections applied to PR wording) |
| Phase 3 — patch quality gate | 12 criteria, CUDA regression, minimal diff | PASS (zero P0/P1; 12/12 platform tests re-run live, 4.47 s) |
| Pre-publish review (×2 rounds) | PR body + comment drafts | PASS after fixing 2 P1 (curl JSON terminator; worktree isolation) |
| Phase 6 — packaging review | python-multipart necessity/cross-platform | PASS (necessary, correct, minimal) |
| Phase 7 — sglang #42106 mapping | Gate-by-gate source mapping | PASS (3–4 guards needed; no overlap with PR-conflicted paths) |
| Final Reviewer A — ROCm/NVIDIA compatibility | Evidence, minimality, CUDA preservation, claims | PASS (5/5 sections) |
| Final Reviewer B — GitHub/maintainer | PR state, body, no duplicates, targeting, H800 actionable | PASS (7/7 sections) |
| Final Reviewer C — evidence/release integrity | Chain, checksums, boundaries, benchmark safety, provenance | PASS (8/8 sections) |

All artifacts under `reports/upstream/session-20261013/` (copied from the session's independent review outputs).

## 4. H800 validation status

**PENDING — external (author).** No NVIDIA GPU execution by our team, ever claimed otherwise. The CUDA fast path is unchanged by construction (every gate reduces to the original expression when `is_rocm()` is false), backed by 12/12 platform tests (re-run this session), 37/37 capability tests, and the 51-case simulated CUDA A/B matrix (recorded receipt). Author asked (comment issuecomment-6144689787) for: isolated worktree test, real `sgl-omni serve` on H800, same request schema/seed, HTTP 200, valid 48 kHz stereo, DeepSelect/CUDA paths active, environment SHA + evidence; explicitly no bit-identical SHA expectation.

## 5. Packaging issue status (isolated from PR #1)

`python-multipart` (0.0.32 used in validation) is an undeclared **platform-neutral** runtime dependency: `create_app` → `register_voices` (openai_api.py:327, route at :363-369) registers File/Form routes unconditionally; FastAPI raises at route registration without the package; reproduced both directions in an isolated venv (fastapi 0.143.0). Fix prepared on **local-only** branch `fix/declare-python-multipart` (commit `daf1a113`, +58/−0: 6 pyproject variants + regression test; verified NOT pushed). Upstream main (cba5a74f) confirmed to lack the declaration → non-duplicate. **Awaiting owner approval before opening a public PR.**

## 6. Original SGLang PR #42106 compatibility status

OPEN, CONFLICTING (DIRTY) with sglang main; CI failing (lint + pr-gate); head `ced0ef7d`. The YuE2 author (a43992899) already validated the BASE PR on NVIDIA (full WSB 384, metrics within tolerance, DeepSelect active). Mapping (full report in `session-20261013/phase7_sglang_mapping.md`): all four Omni gates have NEEDS_GATE counterparts in the PR sources (`song.py:37-39` step-graph, `fastpath.py:50-58` availability, `fa3.py:28,55-57` varlen, pipeline `batched_ar_enabled`); recommended route = propose 3 small capability-keyed guards (using the PR's own `is_deepselect_supported()`) as a follow-up commit to the author's branch AFTER he resolves the main conflicts; patches 0001-0003/0008 target upstream paths outside the PR and belong to a separate track. **No public PR created (per mission: wait for author's preferred integration route).**

## 7. W7900 benchmark status (preserved)

- Run `wsbfull20261012T0041Z` RESUMED_AND_PROGRESSING; driver 493545 (venv verified via /proc), server 487670 (`sglang serve` YuE2-3B @127.0.0.1:31000, port confirmed OPEN), watchers 494130/494132 alive; GPU util 100%, VRAM ~18.5/51.5 GB; disk 62 GB free.
- Verified-complete at closure: **346/384** unique candidates (single run_id; manifest ↔ songs ↔ archive consistent; 345 at audit, 346 at report time). 19 skipped(disk) + remainder pending; gates unchanged: exactly 384 unique, 192×2, strict FULL audit, official scoring only after FULL PASS, evaluator ROCm adaptation disclosed.
- Known hazards: (a) `run_wsb_scoring.sh` still contains broad `pkill -f "sglang serve"` (lines 59-65; live md5 `c2384466607667cebd51a3a8b2f317b8`, unchanged); a PID-scoped replacement is prepared in `/tmp/opencode/scoring-fix/` (patch + syntax-checked fixed copy + README) — deploy ONLY after the running scheduler bash (494132) exits at a safe boundary; never hot-edit a running script; (b) relaunches must activate the benchmark venv (orjson incident documented, not repeated); (c) do not co-schedule other GPU work.

## 8. Maintainer feedback / upstream context

- #2540: OPEN, BLOCKED (REVIEW_REQUIRED; requested reviewer FrankLeeeee; only Copilot bot comments; stale since 2026-10-05). Our patch must land in `add_yue2` first, then ride #2540.
- #42106: see §6; author Yiakwy engaged ("Let's move ahead" to maintainers).

## 9. Next exact actions

- **Author (yiakwy):** run the H800 check on `add_yue2` + 50c91c0 (steps in PR #1 comment); then merge PR #1 into `add_yue2` so it rides #2540.
- **Upstream maintainers (sgl-project):** review/approve #2540 (and later its ROCm-carrying state); separately triage the python-multipart packaging gap once we file it post-approval.
- **Us (after owner approval):** open the standalone packaging PR; deploy the PID-scoped scoring fix at the next safe boundary; prepare the #42106 3-guard handoff for the author.

## 10. Remaining P0/P1/P2/P3

- P0: none open.
- P1: none open.
- P2: (1) `batched.py` lacks a ROCm platform gate — reachable only via `SGLANG_YUE2_BATCH_MAX_SIZE>=2` override, rescued by per-request fallback (pre-existing; follow-up). (2) Broad pkill in scoring script (fix staged, deployment gated). (3) Smoke-window GPU utilization inferential (disclosed in evidence + PR body). (4) 19 skipped(disk) candidates must be re-attempted before 384-closure.
- P3: zombie PID 70945 under PID 1; PR1_HANDOFF_SUMMARY self-cites dd09618 vs tip f000a85 (cosmetic); gradio makes python-multipart transitively present in 3/6 pyproject variants; duplicated import in song.py (pre-existing); #42106 conflict resolution is author-owned.

## 11. Security note (http:// remotes — remediated this session)

`/root/.gitconfig` previously contained `url.http://github.com/.insteadOf=https://github.com/` (and `git@github.com:`) plus `credential.http://github.com.helper=!gh auth git-credential`, rewriting github.com git traffic to plaintext HTTP with a credential helper willing to serve the token for the http scheme. Assessment: configuration-level exposure risk; GitHub's smart-HTTP redirects to HTTPS before auth challenges in the normal flow, and no evidence of token capture was found in logs; treat as unsafe-config incident, not confirmed leak. Remediation: insteadOf rules corrected to https, http credential helper removed, evidence-repo remote set to https, backup retained at `/root/.gitconfig.pre-https-fix.bak`. Recommendation: rotate the GH token at the operator's convenience. Historical evidence and commits untouched.

## 12. Release states (never conflated)

- **AMD_RUNTIME_VERIFIED: PASS** — real Omni W7900 HTTP E2E evidence holds (§2; independently reconciled twice).
- **CROSS_VENDOR_VERIFIED: PENDING** — requires the author's real NVIDIA H800 pass on this commit.
- **UPSTREAM_MERGED: PENDING** — #2540 (and PR #1 into `add_yue2`) are not merged; no announcement before upstream merge + party coordination.
