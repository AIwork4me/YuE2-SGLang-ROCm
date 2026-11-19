# 06 — Security, Licensing and Scientific Provenance (joint-blog-RC)

**Date:** 2026-11-19 · **Scope:** proposed integration tree `integration/joint-blog-rc`
@ `8ebc086` (= PR #15 + M3 analysis).

## Executed checks (all CPU, read-only; raw licensed data never left /data)

| # | Check (mission M6 list) | Tool / method | Result |
|---|---|---|---|
| 1 | Scan proposed integration tree | `public_evidence_guard.py` (structured fields) | **PASS** |
| 2 | Scan ALL tracked text incl. PR-chain changes | `evidence_lyrics_detector.py` tier-1, working tree (347 files) | **PASS** |
| 3 | Identify sensitive text-bearing evidence | FORBIDDEN_KEYS scan (lyrics/transcripts/phonemes/prompt fields) | none present |
| 4 | Historical raw WSB texts must not return | tier-2 ground-truth scan, **1813 distinctive lyric windows** from the SHA-verified frozen manifest (real licensed data, `--require-ground-truth`) | **PASS** — 0 matches |
| 5 | Real-data tier-2 scanning | as above (only possible on hosts with the licensed manifest; CI runs tier-1 only, honestly) | **PASS** |
| 6 | Numeric preservation after redaction | `tests/test_numeric_receipt_integrity.py` + `verify_numeric_receipt_integrity.py` semantics | **PASS** (31 redaction/integrity tests green) |
| 7 | Public score → restricted original mapping | fresh Arm A receipts live under `/data/yue2-runs/...` (restricted); repo carries aggregates + hash anchors only; C2 audio-identity chain (mp3/flac sha256) in receipts | **PASS** |
| 8 | Hashes, protocols, source attribution preserved | integrated tree = #12 provenance stack + #13 lineage; `verify_provenance.py --runs armA_wsb_full` | **PASS — 0 violations, 384 legacy records honestly marked, evidence levels reported separately** |
| 9 | No public audio/lyrics redistribution | no `.flac/.wav/.mp3` tracked; new M3 artifacts carry hashes only (`03_AUDIO_TRANSFER_MANIFEST.json` = ids+sha256+bytes) | **PASS** |
| 10 | Residual historical Git-object exposure | documented below — **owner decision pending** | OPEN |

## Historical Git objects (residual risk, unchanged policy)

Pre-#7 commits on old branches still contain text-bearing evidence objects in
server-side history. Per mission rules: **no automatic history rewrite**. The
working-tree gates (tier-1+tier-2) protect every future clone's checkout.
Options for the owner: (a) accept residual server-side history exposure with
documented risk, (b) coordinated history rewrite + force-push at release time
(destructive; needs explicit authorization and branch protection changes),
(c) GitHub support assisted purge. Recommendation: (a) for this RC, revisit
before AMD publication if legal review requires.

## Licensing posture (unchanged, verified still true)

- WildSongBench prompts/lyrics: research-use licensed; **never** republished;
  audio of model performances of those lyrics likewise private-only.
- Transfer of benchmark audio for the M3.2 CUDA cells: private channel only
  (HF private dataset / private object storage) — kit in
  `03_CUDA_REFERENCE_HANDOFF.md` states this explicitly.
- Model weights (YuE2-3B, YuE2-Vae-legacy): used under their license for
  evaluation; attribution maintained in docs/RESULTS.md and EVIDENCE_INDEX.

## Fresh-campaign provenance status

- Arm A fresh (this image): `verify_provenance.py` PASS (legacy-honest).
- Arm B fresh (running, `armB_full_20261119T015756Z`): uses the C2.1
  new-format journal → per-record provenance chain will be verifiable
  end-to-end at audit time (planned in M2.3 closure).

## Verdict

**M6: PASS for the proposed integration tree** (publication-ready evidence
security and licensing review), with one documented owner-decision item
(historical Git objects) that does not affect fresh clones' working trees.
