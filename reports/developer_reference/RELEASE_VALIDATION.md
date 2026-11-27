# RELEASE_VALIDATION.md — v1.0-rc1 validation record

## Local validation (before push; at the final RC6 commit)

| Check | Result |
|---|---|
| Full CPU test suite (generation venv, hardware host) | **585 passed, 3 skipped, 0 failed** (`test_first_audio.py` now skips honestly — historical phase-4 audio absent after image rebuilds; instructions in the skip reason; GPU acceptance of live audio is covered by the RC6 first-song/pilot receipts) |
| New RC6 negative-control suite | 20/20 PASS |
| compileall (scripts/ + tests/) | rc=0 |
| bash -n (all shell scripts) | clean |
| git diff --check | clean |
| public evidence guard | PASS (no blocked text-bearing fields) |
| numeric receipt integrity | PASS (0 discrepancies) |
| secret scan (tracked tree) | PASS (only scanner regex definitions) |
| evidence freeze verify (13,859 files / 81.5 GB) | **0 mismatches** after the full RC6 GPU campaign |
| GPU live validation | first-song FULL_SONG_PASS (+ fresh-clone byte-identical), pilot 1x2 VALID_PILOT_ONLY (2/2, audio 2/2), Q3O smoke PASS (identity-bound), GPU identity negative control DETECTED (exit 3), stale-lock takeover PASS, ASR live fail-closed resume PASS, evaluator workers exercised (SongBench/MuLan/AMC 192/192 on S_V) |

## Exact-HEAD CI (after push)

The final PR comment records: exact tested SHA, workflow run IDs, check
results and timestamps for `cpu` + `q3o-moe-cpu-numerics` (push + PR
events). A stale-SHA CI is never accepted (G01 rule): any later commit
re-triggers the whole receipt.

## Publication status

Release Candidate PREPARED — NOT published (no GitHub Release, no tag, no
joint-publication claim). Publication requires explicit owner
authorization; joint validation additionally requires author/AMD records
that do not exist today.
