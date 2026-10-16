# FINAL INDEPENDENT REVIEWS — Phase 8 (2026-10-16)

Three independent subagent reviews, all read-only, each returning an explicit
verdict. Verbatim summaries below; full transcripts in the session record.

## Subagent A — Benchmark evidence & metric integrity

Scope: pilot/full identity separation, immutable raw evidence, SHA256 anchor
stability, candidate coverage, RTF/speed recomputation from raw JSONL,
published corrections, anti-fabrication checks.

Result: all items CONFIRMED — pilot/ and full/ perfectly run-id separated
(0 cross-matches); all 22 raw-tree hashes match anchors; 38/38 regression
tests pass; 384/192×2/5-truncated coverage verified; bs1 and sweep-C8
RTF/speed recomputed independently and equal to CORRECTED_METRICS.json; old
`rtf_mean` = speed multiplier confirmed 5/5 stages; all five
`raw_input_sha256` pins verified against actual raw files; BS1 GPU-util
honestly labeled NOT VERIFIED.

Issues: none P0–P2. P3: rounding presentation (1.9455→1.946), `__pycache__`
side-effects of test runs, prompt-164 resume worktree (disclosed).

**VERDICT: PASS**

## Subagent B — Software correctness & security

Scope: long-lyrics root cause on base, minimal-fix property, other-TTS-limit
invariance, request safety bounding, YuE2 model-path invariance, CUDA/ROCm
path isolation, absence of kernel changes, CPU test runs.

Result: all items CONFIRMED — base 4096 cap enforcement and 4,114-char
fixture rejection verified; fix is exactly 1 ClassVar (+2 comment lines) via
the only in-repo override mechanism (moss_tts precedent); default 4096 and
all other models untouched; generation hard-bounded by 24576-token context
(semantic clamp + `generate_tokens` prefix+max check + position-embedding
check) regardless of lyrics length; empty/non-string/invalid-limit still
rejected; zero reads of the cap inside the yue2 package; ROCm PR commits
absent from the branch; zero kernel/attention/sampling code in the diff;
49/49 tests pass.

Issues: none P0–P2. P3: pre-existing `abc_max_tokens` overridability
(still context-bounded); fixture provenance accepted as documented.

**VERDICT: PASS**

## Subagent C — Upstream merge readiness

Scope: PR target/branch/head correctness, duplicate-PR check, branch base
parentage, ROCm PR #1 untouched, public-comment accuracy, H800 disclosure,
PR reviewability, handoff completeness, force-push audit.

Result: all items CONFIRMED — PR #2 = base add_yue2, head 4ad6658b
(single commit, 3 exact files, MERGEABLE); PRs #1/#2 fully disjoint file
sets; 4ad6658b parent = live author add_yue2 head 85ae4b73; PR #1 head
still eca7770f, OPEN, MERGEABLE; erratum numbers all match
CORRECTED_METRICS.json; no H800/merge overclaim anywhere; PR #2 body
reviewable; handoff docs complete with HELD-message policy; full reflog
audit shows no history rewrite ever pushed (pre-push local amend only;
local 91dccda1 is a content-identical unpushed sibling of eca7770f).

Issues: none P0–P2. P3: CI checks pending on both PRs (mergeStateStatus
UNSTABLE while mergeable=true) — expected for cross-fork PRs; local
`fix/yue2-rocm-reference` tip reset to eca7770f during this closure to
match the pushed head (done).

**VERDICT: PASS**

## Resolution ledger

| Severity | Count | Status |
|---|---|---|
| P0 | 0 | — |
| P1 | 0 | — |
| P2 | 0 | — |
| P3 | 6 | All informational; one housekeeping item (local branch reset) applied; rest documented, no action required for acceptance |

**ALL P0/P1 RESOLVED — FINAL ACCEPTANCE GRANTED**
