# RC5.1 P0.1.4 — Storage & Backup Risk

Generated: 2026-11-24 (RC5.1 P0.1)

## Verdict

| Item | Status |
|---|---|
| Live campaign storage | `/data/yue2-runs/...` on the container overlay (`/`, 3.5 T, 51% used) |
| Second-volume backup | `/workspace/yue2-rc5-backup/` on `/rgapi-hackathon-27788-4caa92f3.img` (ext4, loop-mounted, 98 G, 2% used) — **separate filesystem from the container overlay** |
| OFF_MACHINE_BACKUP | **BLOCKED_EXTERNAL** — owner previously confirmed no independent backup host; re-requesting one is out of scope |

## What the second volume protects against

- Container image / overlayfs layer replacement (`/data` lives on `/`, the
  writable overlay of the container snapshot; `/workspace` does not).
- Accidental in-container deletion of `/data` (the backup copy is a distinct
  mount with its own superblock).

## What it does NOT protect against

- Host / VM recycling: the backup image file lives on the same physical host
  storage (`/rgapi-hackathon-27788-4caa92f3.img`). Host loss loses both
  volumes simultaneously.
- Same-host restore success is therefore NOT off-machine disaster recovery
  and is never reported as such.

## Current coverage after RC5.1 P0.1

- Campaign `rc5_armB_latest_upstream_20261124T065451Z`: 20/20 candidates in
  `incremental-016` + `incremental-020`, both archives re-verified (size +
  SHA256) on the second volume.
- Restore drill from the second volume: 20/20 candidates, 220 files verified,
  journal-vs-bundles consistent, checkpoint history preserved (`ok=true`).
- Restored copy re-audited with the official verifier: 20/20 PASS, zero
  regeneration triggers.

## Constraint honored

No restricted audio, transcripts or evaluation assets are uploaded to any
external service without owner authorization. Public repo evidence remains
hashes/numeric receipts only.
