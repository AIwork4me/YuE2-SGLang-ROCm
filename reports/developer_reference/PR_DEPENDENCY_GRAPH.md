# PR_DEPENDENCY_GRAPH.md — RC6 D1: full Git topology audit (live, 2026-11-27)

Source: live `gh` API + `git fetch` of `AIwork4me/YuE2-SGLang-ROCm`
(remote main `ba99c4d`, RC5 branch `57e81c2`; every number below re-derived
from the real refs, not from memory).

## 1. Merged into main

| PR | Title | Merged | Note |
|---|---|---|---|
| #3 | omni evidence acceptance closure | 2026-10-16 | merged into `validation/gfx1100-rocm7141` lineage, later carried by #4 |
| #4 | yue2 final merge blocker closure | 2026-10-17 | into main (base branch later absorbed) |
| #5 | public README and evidence navigation | 2026-10-17 | into main |
| #6 | YuE2 attribution + author handoff docs | 2026-10-17 | into main |
| #7 | **security: redact public WSB text-bearing evidence** (owner-authorized C1) | 2026-11-15 | into main (commits 5f1e892, cc54a92, 29252e1, merge ba99c4d) |

## 2. Closed, unmerged

- #1 `validation/gfx1100-rocm7141` (superseded by later validation work)
- #2 `handoff/omni-add_yue2-rocm-pr` (superseded by #4 lineage)

## 3. Open stack (all DRAFT, all MERGEABLE at audit time)

The stack is **linear**: every branch below is an ancestor of PR #19's head
(verified: `rev-list --count <branch>..rc5-branch` = 0 ahead for all), i.e.
PR #19 contains the entire stack's work; the intermediate PRs are cut points
of one cumulative chain:

```
feat/yue2-rocm-publication-readiness (OPEN base of #8/#9; ancestor of the chain)
   ├── #8  fix/w7900-armA-journal-quarantine-20261115   [SIDE BRANCH — 3 commits NOT in the chain]
   └── #9  mission/w7900-fresh-image-final-closure
          └── #10 fix/w7900-cpu-only-risk-closure-20261115
                 └── #11 mission/c2-scientific-provenance-hardening
                        └── #12 fix/c2-1-final-fail-closed-closure        [side cut of #11]
                 └── #13 fix/w7900-fresh-image-resume-hardening
                        ├── #14 mission/joint-blog-rc-m1                  [ancestor; contained]
                        └── #15 integration/joint-blog-rc
                               └── #16 mission/joint-blog-rc2
                                      └── #17 mission/w7900-rc4-repro-reliability
                                             └── #18 mission/w7900-rc4-1-fail-loud-health-evidence
                                                    └── #19 mission/w7900-rc5-latest-upstream-full-reproduction  ← RC6 base
```

Containment audit (ahead of RC5 head / behind):

| Branch | ahead | behind | Classification |
|---|---|---|---|
| feat/yue2-rocm-publication-readiness | 0 | 129 | ancestor — contained in #19 |
| fix/w7900-armA-journal-quarantine-20261115 (#8 head) | **3** | 129 | **side branch, NOT contained** |
| mission/w7900-fresh-image-final-closure | 0 | 107 | contained |
| fix/w7900-cpu-only-risk-closure-20261115 | 0 | 86 | contained |
| mission/c2-scientific-provenance-hardening | 0 | 83 | contained |
| fix/c2-1-final-fail-closed-closure | 0 | 75 | contained |
| fix/w7900-fresh-image-resume-hardening | 0 | 96 | contained |
| mission/joint-blog-rc-m1 (#14 head) | 0 | 93 | contained (side cut) |
| integration/joint-blog-rc | 0 | 51 | contained |
| mission/joint-blog-rc2 | 0 | 44 | contained |
| mission/w7900-rc4-repro-reliability | 0 | 36 | contained |
| mission/w7900-rc4-1-fail-loud-health-evidence | 0 | 23 | contained |
| mission/w7900-rc5-…-full-reproduction | 0 | 0 | PR #19 HEAD = RC6 base |

### PR #8 (the one real divergence)

`#8` head has 3 commits not in the chain (35d9a55 Arm A evidence
preservation/journal recovery/PER-gate claims · 46c6856 pilot PER lyric +
ASR-text redaction · 9a230d5 docs causality corrections). Patch-id check:
**no patch-id matches** anywhere in the RC5 chain — they were never
cherry-picked. Their FUNCTIONALITY is superseded three ways:

1. the public-evidence redaction landed in **main via #7** (owner-authorized
   C1, 2026-11-15) — but note the RC5 chain **does not contain main's #7
   commits** (it is 4 commits behind main, exactly the #7 set); the chain
   instead carries its own guards (`public_evidence_guard.py`,
   `evidence_lyrics_detector.py`, `redact_evidence.py`, regression-tested).
2. journal quarantine/recovery was re-implemented and hardened in the C2/
   C2.1 (#11/#12) and RC4/RC5 lineages (durable journal, supersede-not-
   overwrite, restore drills).
3. the PER-gate causality statements were superseded by the RC5.1 P1.1
   root-cause closure.

**Owner decision required for #8**: close as superseded (recommended, with
this audit as evidence), or explicitly merge it — do NOT leave it dangling.
Public-safety note: the RC6 branch must NOT rebase onto main without
re-running the public-evidence guard suite, because main's #7 redaction and
the chain's guards evolved independently (the RC6 final CI re-runs both
guard suites at the exact HEAD, see the release gate ledger).

## 4. RC6 branch placement

`mission/rc6-developer-reproduction-reference` is created **from 57e81c2**
(PR #19 HEAD, live-audited) — not from main, not rebasing, no force-push,
nothing merged/closed by RC6 itself. PR #19 and the whole open stack remain
untouched; the RC6 PR will stack on PR #19's branch.

## 5. Integration plan (D2)

- Primary: merge order = #19 (or its consolidated successor) → then the RC6
  PR. The intermediate stacked PRs (#8–#18) are historical cut points of one
  cumulative chain; their individual merge would be redundant (content is
  contained in #19) EXCEPT #8's 3 side commits (owner decision, above).
- A consolidated review branch is NOT created in RC6: the stacked history is
  already linear and traceable; carving a new consolidation branch would
  duplicate diffs and burn maintainer attention. Instead the RC6 PR provides
  a per-topic change classification (D2 table in INTEGRATION_PLAN) and the
  stack stays as-is for the owner to merge in order.
- main's #7 redaction commits and the chain's guards coexist: before any
  eventual merge to main, run BOTH guard suites on the merge result (this is
  recorded in the RC6 release gate ledger as a merge-time check).
