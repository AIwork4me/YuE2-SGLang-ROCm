# CPU-only risk closure: checkpointed engineering review

Source review: mission branch `8c242bae644ef8e0517f8c1fb5e4f79e59721684`.
Target: Draft PR #10 onto `mission/w7900-fresh-image-final-closure`.
No W7900 commands were issued; no Arm A campaign was restarted, stopped,
reconfigured, measured, or touched. Latest verified GitHub snapshot 17/384,
not a live progress claim.

## Closed or improved without GPU
- Current-tree benchmark reference lyrics, ASR transcript strings and
  phoneme arrays removed from five scored-evidence documents. All retained
  numeric field values were verified identical in the mutation transaction.
- Full raw 384-row `evidence/per_song.jsonl` removed from the proposed tree;
  unsafe redundant siblings and Arm B pseudo-redacted export removed.
- A strict tracked-evidence scanner and synthetic negative controls are
  added to GitHub Actions. The scanner cannot purge Git history.
- Evidence redaction no longer depends on the length of user text.
- Corrected source/denominator handling for PER 0.0 best-of-two selection and
  disjoint, phoneme-weighted selected-192 subgroup analysis. Official
  `summary.json.selected_candidates` is required for publication-grade
  candidate selection; PER=1 is NOT inferred as empty transcript.
- Publication README/RESULTS/PER RCA updated to distinguish old 384/384
  metrics from new-image 17/384 progress. Missing cause for PER gap remains.
- Release gates G1 (missing evaluator freezes), G3 (13/14 API), G10
  (unresolved physical faults) explicitly BLOCKED until additional evidence.

## Open / needs physical environment
- Running Arm A full 384/384 and official quality scoring.
- Fresh Arm B, Omni, API concurrency/performance on W7900.
- AR-stage Hang and HIP illegal-memory-access independent reproductions.
- `YuE2Pipeline.close()` GPU resource behavior.
- Same-audio vLLM versus ROCm evaluator PER A/B.
- Two empty evaluator pip-freeze files are not acceptable release evidence.
- Public historical Git object and redistributed content legal remediation
  is still required, and must NOT be done by a routine merge.

## Repository policy
No CONTRIBUTING.md/AGENTS.md was found at repository root or in changed
subdirectories at review time. This repo's LICENSE is MIT; third-party
dataset and model licenses are separate and must be respected.
No modifications have been sent to any upstream repository.

## Review and merge safety
Parent mission PR #9 and the on-host campaign remain unchanged.
PR #10 is Draft. Do not merge until exact-head CI is green, reviewer checks
numeric receipt preservation, and publication-security plan is approved.
