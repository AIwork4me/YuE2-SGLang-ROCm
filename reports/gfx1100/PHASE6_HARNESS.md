# PHASE 6 — WSB Test Harness Port + Hardening (gfx1100)

**Status: PASS (GATE 6 met)** · Tests: `tests/test_wsb_full_mode.py` (10/10), `tests/test_wsb_resume.py` (6/6)

## Prior validation bugs — fixed and locked by negative tests

1. **Silent expect-reduction (v1 line ~51):** full mode could lower 384 to the
   number of present rows. v2: full mode *requires* exactly 384 expected
   candidates, 192 unique prompts, candidates {0,1} per prompt; `--expect != 384`
   is itself an error. Locked by `test_pilot_10_of_10_cannot_pass_full_mode`
   and `test_full_383_of_384_rejected`.
2. **Error-list reset (v1 line ~50):** v1 built `problems` during input
   validation, then overwrote it (`results, problems = {}, []`), swallowing
   seed mismatches. v2: a single `problems` list accumulates from start to
   report; every seed is checked against the frozen manifest. Locked by
   `test_wrong_seed_rejected_and_error_preserved`.

## Additional rejections now enforced (+ tests)

duplicated (i,j) entries; unexpected candidate directories (cross-run
contamination); corrupted artifacts (official verify failure);
dataset-revision hash mismatch (fatal by default; `--allow-missing-dataset-hash`
records the problem instead of hiding it); full-mode-with-wrong-expect-flag.
Truncated-but-valid candidates remain acceptable and are counted
(`test_truncated_but_valid_passes`). Subsets must use explicit `--mode pilot`
(verdict PILOT, never FULL).

## Driver hardening (`run_wsb.py` v2)

- portable workspace (`YUE2_WORKSPACE`); no machine paths anywhere
- immutable `run_config.json` identity {platform, gpu, torch, sglang commit,
  dataset/model/VAE revisions, patchset sha256, official config, run_id};
  re-running with a different identity aborts (no run mixing)
- `evaluation_inputs.jsonl` write-once; divergence aborts
- stale/partial candidates **quarantined** (timestamped dir), never deleted;
  journaled as `quarantined(partial)`
- disk-space safety check (default 20 GiB floor, `YUE2_MIN_FREE_GB` override)
  stops the run before artifacts can be corrupted
- SIGINT/SIGTERM graceful stop (finishes in-flight candidate; status
  `interrupted`; summary written)
- status journal: generated/finalized→complete/failed/truncated/pending/retried
- VRAM/GTT poller discovers any `card*` sysfs node, rocm-smi fallback
  (no hard-coded renderD path)
- atomic writes (fsync + rename) for manifests/config
- `finalize_candidate.py` ported off `/home/amd/Desktop` (YUE2_WORKSPACE)

The legacy gfx1151 launcher `serve_yue2_rocm.sh` is preserved as historical
record; the portable pattern is `serve_yue2_gfx1100.sh` (env-driven).

## Test evidence

`YUE2_WORKSPACE=<ws> python -m pytest tests/test_wsb_full_mode.py
tests/test_wsb_resume.py` → **16 passed**. The resume test suite covers
quarantine-not-delete, journaling, summary integrity, run-identity
immutability, write-once inputs, atomicity, and complete-candidate skip logic
(the quarantine test doubles as the crash-safe restart scenario).
