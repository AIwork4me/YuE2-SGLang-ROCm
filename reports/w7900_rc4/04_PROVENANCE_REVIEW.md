# RC4 M4.4 — Provenance Review

Date: 2026-11-22.

## Frozen evidence status (re-verified this session, read-only)

- `verify_provenance.py --runs /data/yue2-runs/armB_wsb_full` → **PASS, 0
  violations**; 384 records classified `LEGACY_PROVENANCE_INCOMPLETE`
  (honestly marked; never upgraded to source-FULL without receipts).
- Evidence levels reported separately and never conflated:
  - worker snapshot: BYTE_HASH_VERIFIED (sha256 recomputed on disk)
  - driver source: RECEIPT_CROSS_CHECKED_ONLY (git-managed; no on-disk snapshot by design)
  - session runtime: RECEIPT_PRESENT
  - legacy records: UNKNOWN beyond run-level receipt
- No upgrade LEGACY→FULL is claimed anywhere; RC3 finding stands.

## Regression coverage (executed this session)

`tests/test_c2_provenance.py` — **35/35 PASS**, including:
- content-addressed worker snapshots; tampering detected;
- snapshots never overwritten; symlink slot refusal;
- legacy runs marked incomplete (not violations) — a record without source
  identity can never verify as source-FULL;
- clean runs verify end-to-end.

## RC4 additions for NEW runs

- `scripts/run_wsb.py` now records `driver_repo_head` (git HEAD of the driver
  repository) inside the immutable `run_config.json` identity, so every new
  RC4 run carries: platform/gpu/torch, run_id, sglang_commit, model/VAE/
  dataset revisions, patchset_sha256, official config, candidates, indices,
  **and driver source HEAD**. Resume identity-mismatch aborts (rc=3) still
  guard against mixing runs. LEGACY runs predate the field and remain honestly
  attributable only at run level (by design, no backfill).

## RC4 run provenance checklist (applied to every new run in this mission)

source HEAD ✓ (run_config.driver_repo_head) · patchset identity ✓
(patchset_sha256) · model/VAE/dataset revisions ✓ · evaluator identity ✓
(protocol.json + environment receipts, hash-gated build) · runtime env ✓
(torch/HIP in run_config; pip freeze archived) · exact seeds/config ✓
(per-candidate rows) · request/result identity ✓ (result.json identity blob,
audio sha256 in score receipts) · artifact hashes ✓ (audio_manifest.jsonl) ·
worker execution identity ✓ (attempt receipts where supported).
