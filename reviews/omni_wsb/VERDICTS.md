# Arm-B (SGLang-Omni WSB) Independent Review Verdicts — 2026-10-16

| # | Review | Scope | Verdict | Notes |
|---|---|---|---|---|
| 1 | Protocol freeze verification (pre-generation) | settings equivalence vs arm A, dataset fidelity, no-model-math proof of instrumentation, artifact schema, immutability gates, pilot isolation | **PASS** | 0 blockers; informational notes on explicit cfg_scale key and abc key omission (effective values identical) |
| 2 | Pilot pipeline verification | 20/20 candidates, artifact hashes, HTTP metadata, official PER/SongBench acceptance of Omni bundles, contamination, parity | **PASS** | exact audio-duration parity arm A vs arm B on all 20 pilot candidates (Δ 0.00 s) |
| 3 | Dataset completeness & provenance (post-generation) | 384/384 coverage, 384 unique identities/flacs, provenance chain, truncated recording, prompt-164 artifacts, journal sanity, HTTP evidence | **PASS** | 384 unique identities, 384 unique flac sha256, 0 quarantine, full raw-WAV chain verified |
| 4 | Scoring integrity | selection rule recomputation, reuse chain, exclusions, metric arithmetic (PER micro/GA/selected PER/MuLan/AMC recomputed from raw rows), report table transcription | **PASS** | selection_mismatch_count=0; all recomputed values match; one transcription fix applied (arm-A selected GA 6.736) |
| 5 | Maintainer-style review | overclaims, instrumentation safety, reproducibility, internal consistency, upstream action framing | **PASS-WITH-NOTES** | 3 P1 + 3 P2 findings — all resolved in this publication: (P1-1) arm-A selected-GA corrected to 6.7364; (P1-2) main-pass session summary retained (now at evidence/omni_wsb/full/main_pass_summary.json after the 2026-10-16 reorganization; referenced at its original top-level path when this review was written) and session scope annotated; (P1-3) WAV digest + this reviews directory added; (P2-4) BS1 report lands before publication; (P2-5) wording changed to "numerically indistinguishable (max delta 0.002)"; (P2-6) runtime_sha256 coverage clause added |

All five reviews PASS (with notes resolved). No unresolved blockers.
