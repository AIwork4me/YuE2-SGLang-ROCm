# omni_wsb evidence directory — scope guide (2026-10-16 reorganization)

This directory holds the evidence for WildSongBench (WSB) song-generation runs of
YuE2 served by `sgl-omni` on AMD Radeon PRO W7900 (gfx1100, ROCm 7.14.1).

## Evidence scopes (distinct — never mix them)

| Scope | Run ID | Candidates | Where |
|---|---|---|---|
| Pilot (10 prompts x 2) | `omni-pilot10x2` | 20 | `pilot/` |
| Full main pass | `omniwsb20261014T1323Z` | 382 complete + 2 failed (prompt 164, HTTP 400 under the generic input cap) | `full/main_pass_summary.json` |
| Full prompt-164 resume (cap-exempt worktree `c853135a`) | `omniwsb20261014T1323Z` | 2 complete | `full/resume_prompt164_summary.json` |
| Full aggregate strict audit | `omniwsb20261014T1323Z` | 384/384 verified complete, 5 truncated-but-valid, 0 missing/invalid | `full/aggregate_audit.json` |
| Full official scoring (PER + SongBench, 384; selected-192 MuLan/AMC) | `omniwsb20261014T1323Z` | 384 scored / 192 selected | `scores_summary.json`, `additional_summary.json` |

## Session note (important)

The full run had TWO serving sessions under one run ID:

1. **Main pass** (2026-10-14T13:23Z .. 2026-10-15T12:44:18Z): 382 candidates
   complete; the 2 prompt-164 candidates failed HTTP 400 because the generic
   Omni speech-input cap (`MAX_SPEECH_INPUT_CHARS=4096`) rejected the 4,194-char
   nested YuE2 input. See `full/prompt164_serving_disclosure.json`.
2. **Prompt-164 resume** (828.2 s): the 2 missing candidates regenerated from a
   cap-exempt worktree whose only delta is
   `Yue2PipelineConfig.max_speech_input_chars=None` (moss_tts precedent).

The raw run tree's on-disk `generation_summary.json` was overwritten by the
resume session; it is archived here UNMODIFIED as
`full/resume_prompt164_summary.json` (`resumed: 382`, `wall_s: 828.2`). It is
NOT a single-session 384-candidate generation record. The main-pass session
summary (83,989.3 s, 382 complete / 2 failed) is preserved separately as
`full/main_pass_summary.json`.

## History of this reorganization

Before 2026-10-16 this directory top level contained the PILOT
`run_config.json`, `generation_summary.json` and `audit.json` (run
`omni-pilot10x2`, 20 candidates) next to FULL-run scoring outputs — an
ambiguity. On 2026-10-16 (branch `fix/omni-evidence-acceptance-closure`) the
pilot files were moved verbatim (`git mv`, byte-identical, see
`EVIDENCE_MANIFEST.json`) into `pilot/`, and exact byte-copies of the full
run's `run_config.json`, aggregate `audit.json` and resume-session summary were
added under `full/`. No artifact content was modified; no scores changed.

## File map

- `pilot/` — pilot artifacts (20 candidates), original bytes preserved.
- `full/` — full-run (384) config, per-session summaries, aggregate audit,
  prompt-164 disclosure, and `source_manifest.json` anchoring the host-local
  ~30 GB raw tree (metadata SHA256s; the 384 WAVs stay host-local, see
  `RAW_DATA_LOCATION.md`).
- `scores_summary.json` — official PER + SongBench scores, full 384 arm and
  selected 192 arm.
- `additional_summary.json` — MuLan + AllMusicCaps scores on the selected 192
  (candidates reused from the PER/SongBench selection).
- `selected_candidates.json` — the 192 selected (prompt, candidate, seed,
  audio SHA256).
- `anchors.json` — SHA256 anchors of the full-run raw artifacts (unchanged).
- `wav_verification_digest.json` — all 384 raw server WAVs re-hashed and
  matched to the HTTP journal.
- `serving/` — BS=1 and C=1/2/4/8 concurrency benchmark client, summaries and
  (since 2026-10-16) `CORRECTED_METRICS.json` with corrected RTF/speed
  labeling.
- `bench_tooling/`, `logs/` — exact benchmark/scoring tooling and session logs.

## Integrity anchors (full run, see anchors.json + EVIDENCE_MANIFEST.json)

- `run_config.json` sha256 `8eeeb4c46f8aeefdf952875ede08c826c3590c660965422acd84131da7846176`
- `evaluation_inputs.jsonl` sha256 `a906ab391bf80992549fafd4b12631ec335963676d67fd790d30c39d588ac100`
- `generation_manifest.jsonl` sha256 `92ef0148f948efddcdfc3b10e98c116af08b686c7c6b2273f5aacd0dff7471fb`
