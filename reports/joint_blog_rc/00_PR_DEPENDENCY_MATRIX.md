# PR Dependency Matrix — verified live 2026-11-19 via `gh pr list` + git refs

```
main (ba99c4d)
 └─#7 MERGED security/redact-historical-wsb-lyrics-20261115   [public hygiene fix — must survive]
 
feat/yue2-rocm-publication-readiness
 ├─#8 OPEN  fix/w7900-armA-journal-quarantine-20261115        [Arm A evidence preservation]
 └─#9 OPEN  mission/w7900-fresh-image-final-closure           [fresh-image campaign base]
     ├─#10 OPEN fix/w7900-cpu-only-risk-closure-20261115      [CPU risk closure]
     │   └─#11 OPEN mission/c2-scientific-provenance-hardening [C2 provenance]
     │       └─#12 OPEN fix/c2-1-final-fail-closed-closure     [C2.1 fail-closed; HEAD aa3f34f]
     └─#13 OPEN fix/w7900-fresh-image-resume-hardening        [image-swap resume; HEAD f7fda39]
                                                                 ← LIVE CAMPAIGN CHECKOUT
```

## Facts verified this session

- #13 head `f7fda39` = live checkout HEAD (git log). CI run 44421080608 on this
  head: 135 passed / **5 failed** / 26 skipped (TestScoreGate × PermissionError '/data').
- #12 head `aa3f34f` (briefing) — stacked on #11; per handoff, #10 `8756125`,
  #11 `4d9f4a2`, #12 `d66ffbf` at image-swap freeze; heads may have advanced
  since; must re-verify at integration time (M1.4).
- #8 and #9 share base `feat/yue2-rocm-publication-readiness` — divergent
  sibling branches, potential conflict surface in evidence/armA paths.
- #13 is based on #9's branch, NOT on the #10→#11→#12 stack. Two independent
  lineages must be reconciled by merge-base analysis in M1.4:
  lineage-1 = main→feat→#8; lineage-2 = main→feat→#9→{#10→#11→#12, #13}.

## Integration decision (preliminary; validated in M1.4)

Build the RC integration branch from **#13 head** (it is the live campaign
code and contains the newest campaign_ops hardening), then merge **#12 head**
(C2/C2.1 provenance + fail-closed stack), then reconcile **#8** (superseded
quarantine fixes — inspect whether #13 already contains equivalents), then
re-apply any main-only fixes. Preserve: #7 redaction semantics, campaign &
archive identities, protocol locks, evidence attribution.
