# 05_CANONICAL_QUICKSTART.md — RC6 A5.2

The canonical developer quickstart is the repository doc:

> **`docs/QUICKSTART_W7900.md`** (rewritten in RC6 as the single entry point)

Changes vs the RC5.1 state (every item verified against the live tree):

1. **One entry point**: the reference CLI (`scripts/reference_cli.py`) fronts
   every step; manual equivalents are shown but no longer the primary path.
2. **Historical confusion removed from the critical path**: the `ced0ef7d` +
   0001–0005 path and the force-flag matrix moved to an explicit
   *Historical Reference (superseded)* section.
3. **Patch-path breakage fixed**: all `git apply` examples use repo-root
   absolute paths (the old `git -C <upstream> apply patches/...` broke when
   run outside the repo root).
4. **Stale statements corrected**: Q3O "NOT RUN on 48 GB" → the RC5.1
   192/192 ROCm-adapted result with its exact caveat; "vLLM unavailable on
   ROCm" → vLLM 0.19.1 works, 0.14.0 (the official evaluator version) has
   no ROCm build.
5. **First-song acceptance** uses the bundled ORIGINAL lyrics
   (`examples/first_song/`) — legally publishable, unlike WildSongBench
   lyrics.
6. **Verification step is mandatory in the journey** (verdict vocabulary,
   no score-proximity shortcuts).
7. Stale README performance/limitation pointers updated to the RC5.1/RC6
   numbers (see `06_PERFORMANCE_REFERENCE.md`, `06_COMPATIBILITY_MATRIX.md`).
