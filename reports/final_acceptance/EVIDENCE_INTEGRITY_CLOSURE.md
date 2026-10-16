# EVIDENCE INTEGRITY CLOSURE — Phase 1 (2026-10-16)

Branch: `fix/omni-evidence-acceptance-closure` (evidence repo AIwork4me/YuE2-SGLang-ROCm)

## 1. Problem

The published evidence directory `evidence/omni_wsb/` mixed scopes:

- Top-level `run_config.json`, `generation_summary.json`, `audit.json` were the
  **PILOT** artifacts (run `omni-pilot10x2`, 20 candidates, sha256
  `17f8a784…` / `6857977a…` / `4113e5f2…`), sitting next to FULL-run scoring
  outputs (384 candidates). A reader could misread the pilot config as the
  configuration of the 384-candidate run.
- The full run's own `run_config.json` (sha256 `8eeeb4c4…`), aggregate strict
  audit (`846717aa…`) and resume-session summary (`31bcb4ed…`) were not
  published at all — only anchored by `anchors.json` against the host-local
  30 GB raw tree.
- The full run's on-disk `generation_summary.json` was known to be the
  prompt-164 resume-session record (384 complete, 382 resumed, 828.2 s) —
  documenting session separation only in prose.

No scores, raw records, or receipts were wrong; the defect was archival
ambiguity, corrected below without altering any experimental fact.

## 2. Original artifact identification (host raw trees, read-only)

Full run `/workspace/yue2-omni-pr/bench/runs/omniwsb20261014T1323Z` (30.4 GB
tree; 384 WAVs = 16,275,873,792 B):

| Artifact | SHA256 (recomputed 2026-10-16) | Status |
|---|---|---|
| `run_config.json` | `8eeeb4c46f8aeefdf952875ede08c826c3590c660965422acd84131da7846176` | MATCHES expected anchor |
| `evaluation_inputs.jsonl` | `a906ab391bf80992549fafd4b12631ec335963676d67fd790d30c39d588ac100` | MATCHES expected anchor |
| `generation_manifest.jsonl` | `92ef0148f948efddcdfc3b10e98c116af08b686c7c6b2273f5aacd0dff7471fb` | MATCHES expected anchor |
| `scores/per_song.jsonl` | `7e8431f5…40e6` | MATCHES anchors.json |
| `scores/protocol.json` | `5e58f1e3…1428` | MATCHES anchors.json |
| `additional/protocol.json` | `999c9655…a330` | MATCHES anchors.json |
| `scores/summary.json` | `b4396a79…cc9c` | MATCHES anchors.json |
| `additional/summary.json` | `293bac3a…526f` | MATCHES anchors.json |
| `audit.json` (aggregate) | `846717aa…f0a3` | 384/384, 5 truncated-but-valid, verdict FULL |

Pilot run `/workspace/yue2-omni-pr/bench/runs/omni-pilot10x2`: `run_config.json`
(`17f8a784…`, run_id `omni-pilot10x2`), `generation_summary.json`
(`6857977a…`, 20 candidates), `audit.json` (`4113e5f2…`, mode pilot).
The previously published top-level copies were byte-identical to these pilot
originals (verified), i.e. nothing published was fabricated or altered — it was
misplaced.

## 3. Session structure (frozen facts, unchanged)

- **Main pass** (`run-state/main_pass_summary.json`, sha256 `54f3a808…`):
  2026-10-14T13:23Z..2026-10-15T12:44:18Z, 382 complete, 2 failed
  (prompt 164, HTTP 400 under generic 4096-char input cap), wall 83,989.3 s,
  peak VRAM 51,501,813,760 B.
- **Prompt-164 resume** (cap-exempt worktree `c853135a`, single delta
  `Yue2PipelineConfig.max_speech_input_chars=None`): 2 complete, 828.2 s;
  its on-disk `generation_summary.json` (`31bcb4ed…`, `complete: 384`,
  `resumed: 382`) is archived **unmodified** as
  `full/resume_prompt164_summary.json` and is explicitly NOT a single-session
  384-candidate generation record.
- **Aggregate strict audit**: 384/384 verified complete; 192 unique prompts;
  2 candidates/prompt; 5 truncated-but-valid (`wsb_113_r1`, `wsb_133_r0`,
  `wsb_139_r1`, `wsb_164_r0`, `wsb_164_r1`); 0 missing or structurally
  invalid. The generation manifest contains 768 rows = 384 final records plus
  superseded attempts (including the 6 failed prompt-164 attempts retained as
  `generation_failed` rows) — no silent exclusion.

## 4. Reorganization performed (git mv + exact copies; zero content edits)

```
evidence/omni_wsb/
  pilot/  run_config.json generation_summary.json audit.json     (git mv, pilot scope)
  full/   run_config.json main_pass_summary.json
          resume_prompt164_summary.json aggregate_audit.json
          prompt164_serving_disclosure.json source_manifest.json
  README.md  EVIDENCE_MANIFEST.json          (new metadata)
  anchors.json scores_summary.json additional_summary.json
  selected_candidates.json wav_verification_digest.json  (unchanged)
  serving/ logs/ bench_tooling/              (unchanged)
```

- All `git mv` moves and new copies verified byte-identical to host originals
  post-move (SHA256 in `EVIDENCE_MANIFEST.json`).
- `full/source_manifest.json` (generated 2026-10-16) anchors every metadata
  file of the host raw tree plus WAV count (384) / bytes; the 30 GB raw tree
  itself stays host-local per `RAW_DATA_LOCATION.md`.
- Historical pilot file locations documented in `README.md` +
  `EVIDENCE_MANIFEST.json` (`original_path` per file); the two prose references
  to the old top-level `main_pass_summary.json` path updated with an explicit
  move note (`reports/author_acceptance/OMNI_WILDSOGNBENCH_GFX1100.md`,
  `reviews/omni_wsb/VERDICTS.md`).

## 5. Scoring-receipt verification (recomputation from stored records only)

- `scores/per_song.jsonl`: 384 rows; 192 unique prompts; exactly 2 candidates
  per prompt; every row `status: complete`.
- Selected arm: `selected_candidates.json` = 192 entries, 192 unique prompt
  indices; identical (prompt, candidate) coverage to the 192
  `additional/per_song.jsonl` rows → **PER-selected candidates were reused for
  MuLan/AMC** (`selection_candidate_count: 384`, `full_192_selected_coverage:
  true`).
- Recomputed from per-song rows (independent of stored means):
  - PER micro FULL 384 = Σedits/Σref = **0.24819** (stored 0.248187 ✓)
  - PER micro SELECTED 192 = **0.17608** (stored 0.176080 ✓)
  - SongBench Global Avg FULL = **6.7301**, SELECTED = **6.7323**; all seven
    dimension means reproduce the stored values to 4 decimals (both
    aggregation orders — mean-of-row-averages and mean-of-dimension-means —
    agree).
  - MuLan selected = 0.50803, AMC selected = 0.40595 (stored summaries ✓).
- Conclusion: **all published 384-candidate quality scores are confirmed
  unchanged by this audit.**

## 6. Machine-readable index

`evidence/omni_wsb/EVIDENCE_MANIFEST.json` records, for each of the 39 files:
logical scope (pilot / full-main / full-resume / full-aggregate / scoring /
serving / logs / tooling / meta), original path, archived path, SHA256, run
ID, source commit, candidate coverage, provenance, byte-preservation, verdict.

## 7. Regression tests

`tests/test_evidence_integrity.py` — 24 tests, all passing
(CPU-only, no GPU/network): pilot≠FULL labeling, no pilot run-id under `full/`,
no return of ambiguous top-level files, run-id identity, aggregate-count
invariants (384/192/2/5), session distinction (382 vs resume vs aggregate),
SHA256 anchor stability, cross-arm metric arm-scoping (PER selected < full;
6.7301 vs 6.7323 never interchangeable), selected==MuLan/AMC coverage,
manifest↔disk byte-drift check (no silent overwrites), source-manifest WAV
counts.

Pre-existing suite state: 61 passed / 24 environment-gated (live server, GPU,
sglang module, host lockfiles) — failures are environmental and unrelated to
this reorganization; no test references the moved paths.

## 8. Verdict

- Full-run evidence chain: internally consistent, correctly archived,
  hash-anchored, session-separated.
- Pilot evidence: isolated under `pilot/`, byte-preserved.
- No historical artifact rewritten; scores unchanged.

**GATE: EVIDENCE_CHAIN_VERIFIED — pending independent forensic subagent
confirmation below.**

## 9. Independent forensic review

Independent read-only re-verification (general subagent, 2026-10-16):
byte identity of all 7 moved/copied artifacts vs host originals CONFIRMED
(sha256 pairs listed); no ambiguous top-level artifacts remain CONFIRMED;
regression tests re-run: 24 passed / 0 failed; host recomputation CONFIRMED —
384 rows / 192 prompts / exactly 2 candidates per prompt; full-arm PER micro
76,993/310,222 = 0.24819; full-arm SongBench GA 6.7301; selected-arm
PER 27,312/155,111 = 0.17608 and GA 6.7323; additional per_song = 192 rows
with (prompt,candidate) set exactly equal to the selected set (0 audio-sha256
mismatches); EVIDENCE_MANIFEST spot-check 3/3 sha256+bytes MATCH; doc pointers
updated (one cosmetic §7 pointer list subsequently refreshed too).

**FINAL: EVIDENCE_CHAIN_VERIFIED**
