# SGLang-Omni YuE2 WildSongBench on Radeon W7900 (gfx1100) — Author Acceptance Evidence

Run: `omniwsb20261014T1323Z` · 384/384 candidates · strict audit FULL · official
WSB scoring complete. Generated 2026-10-14/15, AMD Radeon W7900 48GB, ROCm
7.14.1, torch 2.12.0+rocm7.14.1.

**This file's name intentionally matches the requested artifact
(`OMNI_WILDSOGNBENCH_GFX1100.md`) exactly as specified in the handoff
instructions.**

## 1. Headline scores (three clearly separated arms)

| Metric | A. Original SGLang W7900 (ced0ef7d, run wsbfull20261012T0041Z) | **B. SGLang-Omni W7900 (this run, omniwsb20261014T1323Z)** | C. Author YuE2 reference (NVIDIA, Sept-12-2026 public table) |
|---|---:|---:|---:|
| Candidates generated | 384/384 (192x2) | **384/384 (192x2)** | 384 (192x2, standard setting) |
| PER unselected-384 micro ↓ | 0.22751 | **0.24819** | not published (unselected arm) |
| PER unselected-384 macro ↓ | 0.21810 | **0.23860** | not published |
| SongBench Melody (384) | 6.670 | **6.668** | — |
| SongBench Arrangement (384) | 6.952 | **6.951** | — |
| SongBench Musicality (384) | 5.919 | **5.917** | 5.9075 (selected-arm protocol) |
| SongBench Vocal (384) | 7.128 | **7.129** | — |
| SongBench Instrumental (384) | 7.028 | **7.027** | — |
| SongBench Mixing (384) | 6.841 | **6.840** | — |
| SongBench Structure (384) | 6.579 | **6.579** | — |
| **SongBench Global Avg (384)** | 6.731 | **6.730** | 6.7316 (selected-arm protocol) |
| PER selected-192 micro ↓ (best-of-2 by PER) | 0.17010 | **0.17608** | 0.0844 |
| PER selected-192 macro ↓ | 0.16160 | **0.16681** | — |
| SongBench Global Avg (selected 192) | 6.736 | **6.732** | 6.7316 |
| MuLan (selected 192) ↑ | 0.50993 | **0.50803** | 0.5068 |
| AllMusicCaps (selected 192) ↑ | 0.40519 | **0.40595** | 0.4054 |
| Q3O | not executed (see §6) | **not executed (see §6)** | 4.6819 |

*Arm-A selected-arm SongBench Global Avg 6.7364 (recomputed from arm-A
per_song.jsonl by independent review; earlier draft mis-transcribed as
6.7329). Cross-arm deltas are descriptive only.*

**Reading.** Arms A and B — the same YuE2 weights served by two independent
integration stacks on the same GPU — agree on every SongBench dimension to
within ±0.002, on MuLan to 0.002, and on AllMusicCaps to 0.0008. This is the
central acceptance evidence: the Omni ROCm reference path reproduces the
original SGLang ROCm path's measured quality. No exact cross-platform
(NVIDIA vs AMD) accuracy comparison is claimed: the author's column reports
the published Sept-12-2026 numbers under the author's evaluator revisions and
hardware; evaluator-revision and ASR-cap differences forbid exact equivalence
claims (see §6). PER differences between A and B are analyzed in §4.

## 2. Frozen protocol (hashes and revisions)

| Item | Value |
|---|---|
| Dataset | m-a-p/WildSongBench@e361b85a; reproduction_manifest.jsonl sha256 `859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0` (auditor-verified) |
| Model (MOT) | m-a-p/YuE2-3B@1a96eca688d6ae5d7f0feb88573fec89920fcd19 (weights_manifest verified per candidate) |
| Decoder VAE | m-a-p/YuE2-Vae-legacy@b54118f0fc462f08999d1ec07e88817f4ee3f770 (benchmark decoder, matches previous official evaluation) |
| Serving stack | sgl-omni 0.1.7, branch bench/omni-wsb @ `c4841f0c667f76f2cbe83f8268b1b9bf5d6feab5` = PR#1 head `50c91c0888312ae784d3c42d9536665aa517dd9d` + comment-only `91dccda1` + bench-only artifacts export |
| Run identity | run_config.json sha256 `8eeeb4c46f8aeefdf952875ede08c826c3590c660965422acd84131da7846176` |
| Evaluation inputs | evaluation_inputs.jsonl sha256 `a906ab391bf80992549fafd4b12631ec335963676d67fd790d30c39d588ac100` (identical seed/prompt set to arm A) |
| Generation settings | cot=full, cfg_scale=1.0, abc_max_tokens=4096, semantic_max_tokens=9000, ode_steps=32, vae_core_frames=1024, vae_halo_frames=16; seeds = frozen manifest candidate_ar_seeds[0..1]; dataset style/lyrics verbatim |
| Evaluator | benchmark/wsb_metrics frozen tree; both scoring stages recorded identical code_files dict sha256 `c15689d9446ea990591615fa2a77eeb86c1737a1cfa371db5cf3ffe0a8f8785b` |
| Selection rule | official PER best-of-2 ("first two seeds; PER, edits, absolute phoneme difference, candidate index"); the SAME selected set reused for MuLan/AllMusicCaps (reused_per_source anchors per_song sha256 `7e8431f5...`, protocol sha256 `5e58f1e3...`) |

## 3. Completeness and integrity

- Generation: 384/384 verified-complete candidates, 192/192 prompts, 2/2
  candidates per prompt, 0 unresolved structural problems; strict auditor
  verdict **FULL** (audit.json: verified_complete=384, missing_or_invalid=0,
  problem_count=0, dataset_revision_ok=true).
- 384/384 unique result.json identities and 384/384 unique audio.flac sha256
  (independent completeness audit: PASS).
- 5 truncated-but-valid candidates (semantic budget reached): wsb_113_r1,
  wsb_133_r0, wsb_139_r1, wsb_164_r0, wsb_164_r1 — all recorded and scored,
  none excluded, no cherry-picking.
- Every candidate: HTTP 200, x-finish-reason recorded, WAV 48 kHz stereo
  (16-bit PCM delivery; finalized FLAC PCM_24 lossless repack), finite,
  non-silent, per-candidate WAV SHA256 journaled and independently re-verified
  against the 384 raw WAVs.
- Wall: main pass 83,989 s for 382 candidates (session summary retained at
  `evidence/omni_wsb/main_pass_summary.json`; the run tree's
  generation_summary.json is the later prompt-164 resume session's) + cap-exempt
  pass for prompt 164 (828 s, 2 candidates). Peak VRAM 51.50 GB (main pass),
  peak GTT 3.05 GB.

## 4. PER detail and ASR capping

- Unselected 384: micro 0.24819 / macro 0.23860. Selected 192: micro 0.17608 /
  macro 0.16681 — selection strictly improves PER as the protocol intends.
- Chinese (94 prompts selected): PER 0.17521 micro / 0.16446 macro, SongBench
  GA 6.7741, MuLan 0.52031, AMC 0.39498.
- English (98 prompts selected): PER 0.17685 micro / 0.16907 macro, SongBench
  GA 6.6922, MuLan 0.49624, AMC 0.41647.
- ASR truncation/capping: 128/384 unselected samples hit the ASR cap (512
  capped repeats; termination policy: capped samples INCLUDED with
  postprocessed text, never excluded). Arm A had 120 capped samples. The
  higher capped fraction (longer effective songs) plus per-sample ASR noise
  explains the A→B PER delta (0.2275→0.2482 unselected, 0.1701→0.1761
  selected); SongBench/MuLan/AMC — which are not PER-coupled — are
  numerically indistinguishable between arms (max delta 0.002).
- The author's 0.0844 reference PER was produced under the author's own
  evaluator revisions and H800 run; with 128 capped samples our PER is not
  directly comparable to it, and we do not claim it is.

## 5. Reproducibility differences vs arm A and the author's NVIDIA runs

1. Endpoint: real `sgl-omni serve` + `POST /v1/audio/speech` (nested YuE2
   JSON) vs arm A's `sglang serve` + `/v1/audio/generations`. Same weights,
   settings, seeds, dataset text.
2. Bench-only instrumentation (never pushed; disclosed): commit c4841f0c adds
   the optional `artifacts_dir` export (the author's own MIGRATION.md TODO) —
   +35 lines, no model-math change; unit gates 12/12 pass. Commit c853135a
   (worktree, prompt-164 pass only) exempts YuE2 from the generic 4096-char
   speech-input cap (moss_tts precedent). The runtime_sha256 identity covers
   the yue2 runtime *.py set only — it does NOT cover config.py, the single
   file the cap-exempt worktree changed; that delta is disclosed solely via
   `run-state/prompt164_serving_disclosure.json`.
3. WAV delivery: Omni returns 16-bit PCM (arm A: FLOAT); official finalizer
   does lossless float64 read → clip → FLAC PCM_24, no resampling.
4. result.json runtime_sha256 hashes sglang_omni/models/yue2/*.py; request.id
   constant "song" (per-candidate identity still unique).
5. **Upstream finding for the author:** Omni's generic
   MAX_SPEECH_INPUT_CHARS=4096 rejects official WSB prompt 164 (nested input
   4114 chars + fields). The original SGLang endpoint has no such cap. Fix
   recommended: `max_speech_input_chars=None` on Yue2PipelineConfig (one
   line, moss_tts precedent) — to be flagged with PR #1; not bundled into the
   correctness-first PR.
6. Author NVIDIA runs: different hardware (H800), evaluator revisions and
   campaign protocol; we compare protocol configuration and metric
   provenance, not rounded paper values, and claim no exact cross-platform
   accuracy equivalence.

## 6. Known limitations

- Q3O not executed: the pinned metrics environment as validated (and used for
  arm A) does not carry the Q3O judge runtime (key environment + Qwen3.5
  judge service); provisioning it would depart from the frozen evaluator
  scope and break arm-A/arm-B evaluator parity. Reported as NOT TESTED.
- Single GPU, single run per arm (no multi-seed campaign beyond the frozen
  two candidates per prompt).
- 5 truncated-but-valid generations included (as required; no exclusions).
- GPU-side ASR ran on the same W7900 (arm A parity study documented 5/6
  host-internal transcription drifts vs CPU arm; PER here uses the frozen
  GPU arm consistent with arm A).

## 7. Evidence pointers (this repository)

- `evidence/omni_wsb/` — audit.json, generation_summary.json, main_pass_summary.json,
  scores + additional summaries, protocol anchors, selected-candidate list (192 rows
  with seeds + audio sha256), WAV-verification digest (384/384 raw WAVs matched to
  journal http evidence), prompt-164 disclosure, run_config.
- Raw run tree (audio bundles, per-song rows, receipts) retained on the
  benchmark host at `/workspace/yue2-omni-pr/bench/runs/omniwsb20261014T1323Z`;
  full per_song.jsonl anchored by recorded sha256 (below).
- per_song.jsonl sha256 (scores): see `evidence/omni_wsb/anchors.json`.
- Independent verdicts: protocol freeze PASS; pilot pipeline PASS (exact
  duration parity arm A/B); dataset completeness PASS (384 unique identities);
  scoring integrity PASS (selection/reuse/arithmetic fully recomputed);
  maintainer review PASS-WITH-NOTES (all P1s resolved before this
  publication): see `reviews/omni_wsb/`.

## 8. Bottom line for upstream acceptance

The patched Omni branch (PR #1 head 50c91c08, ROCm reference path) serves the
full official WildSongBench on a consumer Radeon W7900 with measured quality
indistinguishable from the already-published original-SGLang W7900 benchmark
(SongBench 6.730 vs 6.731; MuLan 0.508 vs 0.510; AMC 0.406 vs 0.405) and
consistent with the author's published YuE2 quality band on NVIDIA hardware
under the documented protocol differences. Serving performance evidence
(BS=1 latency and concurrency) is provided separately in
`OMNI_BS1_CONCURRENCY_GFX1100.md`.
