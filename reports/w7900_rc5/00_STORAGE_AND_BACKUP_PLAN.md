# RC5 Storage and Disaster-Recovery Plan (W7900, fresh image)

Status legend: PASS / PARTIAL / NOT_RUN / BLOCKED_EXTERNAL.

## 1. What was verified on this machine (2026-11-24 UTC)

| Fact | Value | Source |
|---|---|---|
| System image disk | `/` = containerd overlayfs writable layer (`/nvme1/containerd/data/.../snapshots/<id>`), 3.5 TB disk, 1.8 TB free | `findmnt`, `00_ENVIRONMENT.json` |
| Workspace volume | `/workspace` = loop-mounted ext4, 98 GiB, platform quota 100 GiB | `findmnt`, `AMD_ONECLICK_WORKSPACE_QUOTA` |
| Image disk lifetime | **tied to the container/image lifecycle** (the previous image was deleted; all local assets were lost) | mission brief |
| Workspace volume lifetime | **no documented contract** that it survives image deletion — treated as "second volume, same host", never as off-machine | assessment below |
| Off-machine / object storage | **none authorised**: no rclone/aws/gcloud/azure/restic/borg config, no remote filesystem mounted, egress proxy allow-list blocks arbitrary hosts | `rc5_env_snapshot.py` → `backup_capability` |
| RAM bound for CPU offload | cgroup `memory.max` = 55.0 GiB (host has 503 GiB; the cgroup limit is what counts) | `00_ENVIRONMENT.json` |

**Verdict for the off-machine requirement: `DISASTER_RECOVERY_BLOCKED`.**
Everything that can be executed safely on this host is implemented and
drilled below; the last hop (an authorised destination outside this image)
needs an operator decision (section 6).

## 2. Asset classes

| Class | Examples | Size | Regenerable? | Protection |
|---|---|---|---|---|
| Pinned public inputs | YuE2-3B, YuE2-Vae-legacy, WildSongBench + evaluator bundle, Q3O judge (70.5 GB), ASR/MuLan/AllMusicCaps (11 GB) | ~90 GB | yes, hash-verified re-download (`download_pins.py`, `rc5_download_q3o.py`, `wsb_eval.py prepare`) | pins in `configs/benchmark.rc5.lock.yaml`; no backup needed |
| Software | SGLang tree, venvs, evaluator venvs | ~25 GB | yes, from git + lock files | `02_EFFECTIVE_RUNTIME_MANIFEST.json`, pip freezes |
| **Campaign outputs** | 384 candidate bundles (FLAC + npy + receipts), journals, run identity | ~10.5 GiB | **no** (≈30 GPU-hours; identical only if bit-exact deterministic) | L1–L4 below |
| Intermediate WAVs | server WAV per candidate (PCM_16) | ~18 GiB | from `latent.npy` via the benchmark VAE (GPU time) | not backed up by default; SHA256 journaled |
| Scores / evaluator receipts | PER/SongBench/MuLan/AllMusicCaps/Q3O receipts | < 1 GiB | re-scoring from frozen audio (GPU/CPU time) | evidence bundle + L3/L4 |

## 3. Protection layers actually implemented

* **L1 — crash-durable per candidate** (`scripts/rc5_generate.py`): the bundle is
  built in `staging/`, finalised, verified by the official
  `artifact_storage.verify_result`, fsynced, then published by an atomic
  no-clobber rename; `journal.jsonl` is appended with `fsync` for every
  `launched` / `result` / `checkpoint` / `backup_verified` event. A verified
  candidate is never overwritten; a damaged one is quarantined (moved, never
  deleted) and regenerated with a higher attempt number.
* **L2 — checkpoints**: every 16 complete candidates an incremental
  `incremental-NNN-<utc>.tar.zst` + `.manifest.json` (SHA256 of every file);
  at 32 / 64 / 128 / 192 / 256 / 384 a FULL checkpoint and a
  `restore-manifest-NNN.json` (all candidates, per-file hashes, model and
  dataset pins). Measured: ≈ 22 MiB compressed per candidate (10 candidates →
  224.9 MB in two incrementals); projected 40 GiB for the whole campaign
  including all milestone fulls.
* **L3 — second-volume copy**: each checkpoint is copied to
  `/workspace/yue2-rc5-backup/checkpoints/<run_id>/` and **re-verified there**
  (size + SHA256, journal event `backup_verified`). `rc5_backup.py verify`
  re-hashes every archive member against the manifest.
  *Disclosure: this is the same host. It survives a container restart and a
  rebuilt container image if (and only if) the platform keeps the workspace
  volume; it does NOT survive loss of the host or an operator wiping
  `/workspace`.*
* **L4 — Git**: reports, numeric evidence, manifests and journals without
  lyrics/audio/transcripts go to GitHub (`AIwork4me/YuE2-SGLang-ROCm`). Git
  survives image deletion but is **not** an asset backup.

## 4. Restore drill (executed, not planned)

Source: the **backup copy on the second volume** (never the live run).
Target: an independent directory under `/data/yue2-runs/rc5-restore-drill/`.

```bash
python scripts/rc5_backup.py verify --run-dir /workspace/yue2-rc5-backup/checkpoints/<run_id>
python scripts/rc5_backup.py drill  --from   /workspace/yue2-rc5-backup/checkpoints/<run_id> \
                                     --to    /data/yue2-runs/rc5-restore-drill/<stamp>
```

The drill restores candidate bundles, `journal.jsonl`, `run_config.json` and
`evaluation_inputs.jsonl`, re-hashes every restored file from disk, replays
the journal and checks that the set of candidates with a `result: complete`
event equals the set of restored bundles. Result:
`reports/w7900_rc5/00_RECOVERY_DRILL.json`. Executed twice on 2026-11-24:

* mid-pilot: 8 candidates / 88 files hash-exact, journal 21 events consistent,
  the 4 not-yet-checkpointed candidates correctly reported as missing;
* final pilot drill (4 archives: 3 incrementals + 1 full): **12 candidates,
  132 files hash-exact from disk, journal 31 events, journal ⇄ bundles
  consistent, run identity + 12 evaluation rows recovered**; independent
  cross-check: every restored FLAC equals the live run (12/12) and the
  historical frozen manifest (12/12).

A restored run resumes with the normal command — `rc5_generate.py` audits
existing bundles with the official verifier and regenerates only what is
missing or damaged.

## 5. What a fresh image needs (handoff summary)

1. `git clone` + checkout the exact RC5 commit (see `09_DISASTER_RECOVERY_HANDOFF.md`).
2. `download_pins.py` (SHA256-gated), `rc5_build_generation_env.sh`,
   `rc5_install_sglang.sh`, `git apply patches/rc5-0001-0003-0008-rocm-import-guards.patch`.
3. Restore checkpoints into the new run directory, run `rc5_backup.py verify`.
4. `rc5_supervise.sh <run_dir> <run_id>` regenerates only missing candidates.

## 6. BLOCKED: the off-machine hop

No destination outside this image is authorised. To close G13 an operator has
to provide one and state its class. Ready-to-run options (none executed):

* **Object storage** — export the provider credentials *to the process that
  runs the sync only*, then:
  `rclone copy /workspace/yue2-rc5-backup <remote>:<bucket>/yue2-rc5` followed by
  `rclone check --download` (size + hash re-verification at the destination).
* **Another host** — `rsync -a --info=progress2 /workspace/yue2-rc5-backup/ host:/path/`
  then `ssh host 'cd /path && sha256sum -c SHA256SUMS'`.
* **Private git release assets** (≤ 2 GB per asset; chunks already ≤ ~1.5 GB
  at the 384 milestone) — only with explicit owner approval; never a public repo.

`rc5_backup.py snapshots --from <run_dir>` prints the list of archives with
sizes and SHA256 that must be shipped.

Nothing in this document claims an off-machine backup exists.
