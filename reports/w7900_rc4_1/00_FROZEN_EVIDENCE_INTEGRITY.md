# RC4.1 — Frozen evidence integrity (M0.3)

## Scope

`/data/yue2-runs/armA_wsb_full`, `/data/yue2-runs/armB_wsb_full`,
`/data/yue2-runs/rc4_evidence` — all 15,825 files.

## Method

Full-content SHA256 manifest taken BEFORE any RC4.1 GPU work
(2026-11-22T22:50Z) and re-computed AFTER all RC4.1 experiments
(2026-11-23T00:08Z). Full manifests (2.7 MB) preserved at:

- `/data/yue2-runs/rc4_1_evidence/20261122T2300Z/frozen_manifest_before_20261122T2250UTC.sha256`
- `/data/yue2-runs/rc4_1_evidence/20261122T2300Z/frozen_manifest_after.sha256`

Manifest-of-manifest: `sha256(before-manifest) =
8cefa066151ef5d96d9f304797abf6cab09cc2a3151403ca90af5bf851dc75a4`
(15,825 lines).

## Result

```
diff <(sort before) <(sort after) -> empty
FROZEN EVIDENCE BYTE-IDENTICAL (15825 files)
```

No frozen audit.json, score receipt, audio, log or CSV under the frozen
trees was modified by RC4.1. All RC4.1 experiments used new directories
(`rc4_1_evidence/20261122T2300Z`, `rc4_1_native_pilot/`) and new run_ids.

## Workspace-disk note (transparency)

`/workspace` (NFS scratch, NOT a frozen-evidence location) reached 100%
during this mission. Reclaimed: RC4/RC4.1-era scratch server outputs
(`/workspace/outputs/*.wav` — transient request outputs whose receipts
live under /data/yue2-runs/rc4_evidence logs; this mission's two repeated-
tags RCA wavs were preserved to
`rc4_1_evidence/20261122T2300Z/{0896edc2…,ad84fac2…}.wav` first) and
intermediate wav/flac under `/workspace/rc4_cancel{1,2}`,
`rc4_pilot_armB`, `rc4_perf_armB` (measurement receipts for these live
under /data/yue2-runs/{rc4_evidence,rc4_perf}). Frozen trees untouched
(hash-verified above).
