# 00_STORAGE_RISK.md — RC6 storage risk assessment (M0.4)

## Protected (cannot be cheaply rebuilt)

| Asset | Location | Size | Protection |
|---|---|---|---|
| 384 generated FLACs + per-candidate bundles | `/data/yue2-runs/rc5-latest-upstream-20261124T065451Z/wsb_full/songs` | 8.2 GB | SHA256-frozen (00_EVIDENCE_FREEZE.json), checkpoint archives |
| ASR / PER receipts (transformers + vLLM arms) | `.../wsb_full/per_full`, `/data/yue2-runs/rc5-per-experiments` | 24 MB | SHA256-frozen |
| Q3O receipts (192/192) | `/data/yue2-runs/rc5-q3o` | 8 MB | SHA256-frozen |
| Campaign journals, run_config, evaluation_inputs | `.../wsb_full/*.jsonl/json` | 34.6 GB tree total | SHA256-frozen |
| Same-host second-volume backup (26 archives + manifests) | `/workspace/yue2-rc5-backup/checkpoints/rc5_armB_latest_upstream_20261124T065451Z` | 18.6 GB | SHA256-frozen; restore drill 384/384 verified (2026-11-27) |
| Restore drill image | `/data/yue2-runs/rc5-restore-drill/rc5_1_final_20261127T125802Z` | 28.4 GB | SHA256-frozen |

## Risk statement

- **OFF_MACHINE_BACKUP = BLOCKED_EXTERNAL** (re-confirmed live at RC6 M0; owner
  has no backup host). The second volume lives on the same physical host as the
  primary copy: a host-level failure can destroy both. The restore drill and
  per-file hashes make recovery *verifiable* but not *survivable*.
- Workspace volume (`/workspace`, 98 GB) holds the backup and has 76 GB free.
- Root overlay has 1.6 TB free — RC6 new runs write to `/data/yue2-runs/rc6-*`
  with independent run_ids (never into frozen trees).
- No RC6 experiment may write into any frozen tree; verified before and after
  the mission via `scripts/rc6_evidence_freeze.py --verify`.

## Preflight checklist executed (M0.4)

- Campaign data present: 384/384 (frozen).
- Same-host backup: present, 52 files, hash-verified in the freeze manifest.
- Checkpoint archive: 26 archives (full-384 + 25 incremental), drill 384/384 OK.
- Restore manifest: `RESTORE_RECEIPT.json` (restored 2026-11-27T12:59:49Z).
- Available storage: 1.6 TB (root overlay), 76 GB (workspace volume).
- Restore test status: PASS (final drill receipts in 01_RESTORE_DRILL.json).
- Off-machine: BLOCKED_EXTERNAL — no unauthorized third-party upload performed.
