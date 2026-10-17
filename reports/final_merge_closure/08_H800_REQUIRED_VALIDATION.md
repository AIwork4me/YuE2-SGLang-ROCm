# 08 — H800 required validation (NOT YET PERFORMED)

Status: **NOT TESTED — no physical NVIDIA run exists on any integrated
commit.** Mocked-CUDA platform tests and static analysis are not GPU
execution proof. Nothing in this mission changes that.

## Already verified (separate evidence, do not redo)

- AMD W7900D end-to-end (old-patch and renamed trees, bit-identical output)
- WildSongBench 384/384, serving sweep, long-lyrics validation — see
  `reports/author_acceptance/`, `reports/final_acceptance/`.

## H800 acceptance contract for the integrated commit (after the author
applies report 06 steps 1–5)

1. Serve with `sgl-omni serve --model-path <YuE2-3B>` on H800 (CUDA).
2. Confirm fast-path markers: fast sampler selected (DeepSelect backend),
   AR decode via CUDA graph (step graph when SGLANG_YUE2_STEP_GRAPH=1 and
   cot!=off), FA3-varlen attention via the shared op.
3. POST /v1/audio/speech with the known-good short request → HTTP 200;
   WAV 48 kHz stereo; finite; non-silent; generation completes.
4. No import/attribute errors for the renamed symbols.
5. Optional: one full-song request for sanity; compare quality informally
   with the author's prior CUDA results.

Receipt template: `merge_readiness/05_H800_ACCEPTANCE_CHECKLIST.md`.

## Distinction that must survive in all public statements

- OLD_PATCH_RUNTIME_PASS — W7900D evidence on pre-closure trees.
- NEW_RENAMED_SOURCE_RUNTIME_PASS — W7900D evidence on b91b95440
  (bit-identical to old tree; this mission).
- H800 RUNTIME — **does not exist yet**.
