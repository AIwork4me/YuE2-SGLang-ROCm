# RC4 M4.3 — Truncated-but-Complete Candidate Audit (five Arm B + Arm A semantics)

Date: 2026-11-22. Read-only audit of frozen evidence; nothing re-scored or
modified. Hash baseline: `/data/yue2-runs/rc4_evidence/frozen_manifests_20261122.txt`.

## Concept separation (as required)

- `ARTIFACT_COMPLETE` — all required artifacts present and decodable
  (audio.flac + 10 sidecars; ffprobe-valid).
- `GENERATION_NATURAL_END` — every autoregressive stage ended on EOS before
  any token cap.
- `GENERATION_TRUNCATED` — at least one stage ended by its token cap
  (semantic_max_tokens=9000 or abc_max_tokens=4096), yet the artifact decoded
  into complete, valid audio.
- `ASR_CAPPED` — PER-scoring-time transcription length capping (a scoring
  property, e.g. `selected_asr_truncated_samples` in summary.json).
  **Not** a generation property; never conflated below.

## Arm B (`armB_full_20261119T015756Z`) — the five reported candidates

All five: semantic stage ended naturally (4835–8916 content tokens < 9000);
**ABC stage hit the 4096-token cap**; audio fully decoded; 11/11 artifacts;
ffprobe `flac` + duration matches receipt.

| redacted id | seed | sem tokens | abc tokens | stage truncated | audio s | verdict |
|---|---|---|---|---|---|---|
| wsb_113_r1_s831132 | 831132 | 4835 | 4096 (=cap) | abc | 193.4 | ARTIFACT_COMPLETE + GENERATION_TRUNCATED(abc) |
| wsb_133_r0_s831134 | 831134 | 8916 | 4096 (=cap) | abc | 356.6 | same |
| wsb_139_r1_s831158 | 831158 | 6971 | 4096 (=cap) | abc | 278.8 | same |
| wsb_164_r0_s831165 | 831165 | 7620 | 4096 (=cap) | abc | 304.8 | same |
| wsb_164_r1_s831183 | 831183 | 7889 | 4096 (=cap) | abc | 315.6 | same |

Interpretation: valid, decodable, officially-FULL outputs whose generation
ended at the ABC (codec-conditioning) limit rather than naturally. Musical
"completeness" is not asserted — the official frozen audit criteria accept
them as complete artifacts, and this audit does not change that.

## Arm A (`armA_wsb_full`) — manifest records per-stage dicts

5 of 384 rows carry any `true` in `{"abc": b, "semantic": b}`:

| redacted id | sem tokens | abc tokens | truncated stages | audio s |
|---|---|---|---|---|
| wsb_086_r0_s831087 | 9000 (=cap) | 2469 | semantic | 360.0 |
| wsb_118_r1_s831137 | 9000 (=cap) | 2977 | semantic | 360.0 |
| wsb_164_r1_s831183 | 9000 (=cap) | 4096 (=cap) | semantic+abc | 360.0 |
| wsb_095_r0_s831096 | 8790 | 4096 (=cap) | abc | 351.6 |
| wsb_113_r1_s831132 | 6670 | 4096 (=cap) | abc | 266.8 |

Cross-arm corroboration: prompts 113 and 164 produce capped generations on
**both** backends → truncation is prompt-length-driven (long lyrics), not a
backend defect. Semantic-cap rows decode to exactly 360.0 s (the config's
semantic budget ⇔ duration ceiling).

## Frozen audit.json discrepancy (documented, NOT modified)

`armA_wsb_full/audit.json` (generated 2026-11-18T11:03Z) records
`truncated_but_complete: 384` — produced by the pre-fix auditor whose
`is_truncated` treated any non-empty dict (Arm A's all-false dicts included)
as truncated. The fix (commit `86355b3`, 2026-11-22, RC3) landed **after**
that audit ran. Recomputing with the current code path (read-only, results
NOT written into the frozen tree): **Arm A truncated_but_complete = 5**,
matching the manifest exactly. Arm B's frozen audit.json (5) was produced
post-correct-semantics and stands unchanged.

No frozen file was modified; the stale Arm A count is documented here as a
historical artifact of the pre-fix auditor.

## Conclusions

1. Arm B: 5/384 generation-level truncated (all ABC-stage); 0 missing/invalid
   artifacts; officially FULL; distinct from ASR_CAPPED counts in scoring.
2. Arm A: likewise 5/384 (3 semantic, 3 abc, 1 both) under corrected counting.
3. Truncation correlates with long-lyrics prompts across both backends.
4. No criterion, score, or frozen artifact was changed retrospectively.
