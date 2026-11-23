# RC4.1 — Public evidence index

All public-safe RC4.1 artifacts. No lyrics, transcripts, audio, weights or
secrets are published; the public-evidence guard and lyrics detector PASS
on the final tree.

## In-repo (this PR)

| Artifact | Content |
|---|---|
| `reports/w7900_rc4_1/00_LIVE_STATE.md` | mission-start audit |
| `reports/w7900_rc4_1/00_BASELINE_SHA.json` | base SHA / PR topology |
| `reports/w7900_rc4_1/00_FROZEN_EVIDENCE_INTEGRITY.md` | 15,825-file hash protection proof |
| `reports/w7900_rc4_1/01_GPU_FALLBACK_RCA.md` | suspect re-analysis + identity chain |
| `reports/w7900_rc4_1/01_GPU_IDENTITY_MATRIX.csv` | full verification matrix |
| `reports/w7900_rc4_1/01_FAIL_LOUD_TESTS.md` | fail-loud inventory |
| `reports/w7900_rc4_1/01_GPU_VERDICT.json` | machine verdict |
| `reports/w7900_rc4_1/02_HEALTH_RCA.md` | health blind spots + FSM |
| `reports/w7900_rc4_1/02_WORKER_LIVENESS_MATRIX.csv` | liveness matrix |
| `reports/w7900_rc4_1/02_IDLE_SPIN_REPRODUCER.md` | upstream reproducer (authorized-owner draft) |
| `reports/w7900_rc4_1/02_HEALTH_VERDICT.json` | machine verdict |
| `reports/w7900_rc4_1/03_INPUT_RCA.md` | repeated-tags RCA (test-harness budget defect) |
| `reports/w7900_rc4_1/03_LIFECYCLE_TESTS.md` | lifecycle/lock tests |
| `reports/w7900_rc4_1/03_LOCK_OWNERSHIP.md` | per-session lock receipts |
| `reports/w7900_rc4_1/03_INPUT_TEST_MATRIX.csv` | input matrix |
| `reports/w7900_rc4_1/04_EVIDENCE_DISCREPANCIES.md` | found+fixed list |
| `reports/w7900_rc4_1/04_RECONCILIATION.json` | machine reconciliation |
| `reports/w7900_rc4_1/04_README_REVIEW.md` | docs review |
| `reports/w7900_rc4_1/05_*` | review, mutations, PR17 review, gate ledger, handoff |
| `reports/w7900_rc4_1/FINAL_REPORT_ZH.md` | final Chinese report |
| `reports/w7900_rc4/0{2,3}_*.csv` | the three formerly-missing RC4 CSVs (committed RC4.1) |
| `scripts/{gpu_identity,server_readiness,input_budget,verify_rc4_evidence_consistency,mutation_controls_rc41}.py` | new tooling |
| `scripts/campaign_ops/run_with_server.sh` | lifecycle wrapper |
| `tests/test_{gpu_identity,server_readiness,input_budget,run_with_server,evidence_consistency_rc41}.py` | 44+13 new tests |

## Host-side (private evidence, hashed)

`/data/yue2-runs/rc4_1_evidence/20261122T2300Z/` — raw receipts
(phase_a/b1/b2 logs+JSON, gpu-identity JSONs, native pilot log),
`/data/yue2-runs/rc4_1_native_pilot/` (official-protocol artifacts incl.
audio; NOT published — CC BY-NC model output), frozen-evidence manifests.
Classification: PRIVATE_EVIDENCE_WITH_PUBLIC_RECEIPT (public reports carry
the measured numbers; raw audio/logs stay on the rig).
