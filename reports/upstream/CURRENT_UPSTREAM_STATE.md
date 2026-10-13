# CURRENT_UPSTREAM_STATE.md — 2026-10-13 (Phase 1 independent audit)

Auditor: independent subagent (read-only GitHub verification), cross-checked by operator.
All SHAs verified live via GitHub API on 2026-10-13.

## PR #1 — ours (ROCm minimal patch)

- URL: https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1
- State: OPEN / **DRAFT**
- Head: `fix/yue2-rocm-reference` @ `50c91c0888312ae784d3c42d9536665aa517dd9d` (verified = AIwork4me fork branch)
- Base: `add_yue2` @ `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9` (verified unchanged; author branch tip, last push 2026-10-05)
- mergeable: MERGEABLE; mergeStateStatus: UNSTABLE (cause: no CI checks configured on fork, not conflicts)
- Reviews: none. Review requests: none. Comments: none. CI: no checks reported.
- Files: 5 (+237/−6) — stages.py, song.py, fastpath.py, fa3.py, test_yue2_platform_gates.py
- No author integration yet: `is_rocm` appears 0 times in author's add_yue2 yue2 sources (verified via contents API). No duplicate ROCm PR exists on either fork (all-states search).

## PR #2540 — author's Omni carrier (sgl-project/sglang-omni)

- URL: https://github.com/sgl-project/sglang-omni/pull/2540
- State: OPEN, not draft; head `add_yue2` @ `85ae4b73` (same SHA as PR #1 base)
- mergeable: MERGEABLE; mergeStateStatus: BLOCKED (REVIEW_REQUIRED; requested reviewer FrankLeeeee; only Copilot bot comments)
- No inline review comments, no human issue comments, no CI runs. Stale since 2026-10-05.

## PR #42106 — original SGLang (sgl-project/sglang)

- URL: https://github.com/sgl-project/sglang/pull/42106
- State: OPEN; head `add_yue2` @ `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`
- mergeable: **CONFLICTING** (mergeStateStatus DIRTY — conflicts with sglang main)
- CI rollup: FAILURE (lint + pr-gate). 17 reviewers requested, 0 human reviews.
- Human comments: yiakwy cc'd YuE2 author (a43992899); YuE2 author posted a full positive WSB E2E parity evaluation (384 candidates, DeepSelect active, metrics within tolerance, 2026-10-04) and yiakwy replied "Let's move ahead" pinging maintainers (@merrymercury @ShenAo1111 @BBuf @zhaochenyang20 — sic).

## Actual merge blockers for PR #1 (evidence-cited)

1. PR #1 is DRAFT (GitHub hard-blocks merge of drafts) — ours to fix after gates.
2. Zero reviews / no review requests on PR #1 — author action needed.
3. No CI on the fork (UNSTABLE) — informational only; tests executed locally (12/12 platform, 37/37 capability).
4. Contextual: carrier PR #2540 itself is REVIEW_REQUIRED upstream; PR #1 must land in `add_yue2` first, then ride #2540 to main.
5. PR #42106 has unresolved conflicts with sglang main (separate track, do not conflate with the Omni path).

## Conclusion

The author has NOT integrated our patch; base SHAs are unchanged; no duplicate work exists.
Next actions: update PR #1 body with verified W7900 HTTP E2E evidence, transition Draft→Ready,
post the H800 verification request (Phases 4–5). Author merge into add_yue2 and H800 run are external.

PHASE1_VERDICT: BLOCKED (as-is) — blockers 1–2 are actionable by us now; 4–5 are external and tracked.
