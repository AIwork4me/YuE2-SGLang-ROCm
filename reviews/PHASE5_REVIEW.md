# PHASE 5 Independent Review — WildSongBench Pilot (generation + official evaluator)

**Reviewer:** independent verification subagent
**Date:** 2026-10-12
**Scope:** `reports/PHASE5_WSB_PILOT.md` and all Phase 5 artifacts under
`/home/amd/Desktop/YuE2/runs/wsb_pilot/`, `/home/amd/Desktop/YuE2/scripts/`,
`/home/amd/Desktop/YuE2/evidence/YuE2-SGLang-ROCm/` (evidence, patches),
`/home/amd/Desktop/YuE2/benchmark/WildSongBench/`.
**Method:** static/artifact-based only (per instruction: no GPU workloads, no
server restarts, no evaluator runs). All checks below were re-executed from
scratch by this reviewer with the yue2 venv python: fresh `verify_result` /
`validate_generation` calls over all 10 candidates, fresh sha256 digests, fresh
tarball extraction into `/tmp/wsb_verify`, JSON cross-checks, git history
inspection. Nothing was taken on trust from the implementer's own numbers.

## Verdict

# PASS

All eight mandated checks verify against the artifacts. Two issues found and
filed below: a P1 (the committed report's "evaluator scored 10/10" bullet is
contradicted by the scoring artifacts — only the 2 prompt-0 candidates were
scored; the 8-candidate re-score was aborted; `pilot_validation.json` states
this correctly) and a P2 (stale `identity` fields in the run manifest for the
2 re-finalized stage-1 candidates). Neither invalidates the phase gate claims
that are actually supported: 10/10 candidates generated and verified against
the frozen evaluator schema, and the official evaluator executed end-to-end
(shard mode, 2 candidates) with disclosed, hash-accounted portability patches.

## Independent verification results

### 1. Generation manifest — PASS

`/home/amd/Desktop/YuE2/runs/wsb_pilot/generation_manifest.jsonl`:

- 12 lines = 10 full records + 2 `complete(resumed)` markers for the two
  stage-1 ids (`wsb_000_r0_s831001`, `wsb_000_r1_s831019`), appended when the
  stage-2 run skipped the already-complete stage-1 candidates. This matches
  the report ("2 resumed") and the resume design; noting it because the file
  therefore contains 2 duplicate-id marker lines without
  wall/truncated/identity detail (P3-1).
- The 10 full records cover exactly `wsb_{000,001,002,076,077}_r{0,1}` with
  seeds `831001+i` / `831019+i` — verified against the official formula in
  `/home/amd/Desktop/YuE2/benchmark/WildSongBench/code/generate.py`
  (`bases=[831001, 831019, ...]`, `seed = base + prompt_index`,
  `candidate_ar_seeds == candidate_nar_seeds` re-verified row-by-row in the
  official `reproduction_manifest.jsonl`).
- Statuses: ten `complete`, two `complete(resumed)`, zero
  `generation_failed`/`finalize_failed`. All 10 full records carry
  `wall_s`, `audio_seconds`, `truncated`, `codec_frames`, `identity`.
- `generation_summary.json`: expected 10 / complete 10 / failed 0 /
  pending 0, wall 6348.0 s, peak GTT 28 563 648 512 B (= 26.6 GiB; report
  says 28.6 — that is 28.6 GB decimal, consistent).
- Evidence copy is byte-identical:
  `sha256(evidence/pilot_manifest.jsonl) == sha256(runs/wsb_pilot/generation_manifest.jsonl)
  == 0029675d10b0613ed105292fd6d0ecc2bf3775a480a2c6967893cb5d6c887435`.

### 2. Evaluator inputs — PASS

`/home/amd/Desktop/YuE2/runs/wsb_pilot/evaluation_inputs.jsonl`: exactly 10
rows, keys and key order (`prompt_index`, `candidate_index`, `seed`, `path`)
byte-format match to the official driver's writer in `code/generate.py`
lines 64-68; ids/seeds identical to item 1; paths `songs/<ident>` all exist.

### 3. Per-candidate official verification — PASS (all 10, not just 3)

Executed with `/home/amd/Desktop/YuE2/environments/yue2/bin/python`,
`sys.path.insert(0, benchmark/WildSongBench/wsb_metrics)`, over **all 10**
candidate dirs:

- `artifact_storage.verify_result(dir)` → PASS for 10/10 (status complete,
  required artifacts present, byte sizes + sha256 of every artifact match
  `result.json["artifacts"]`).
- Evaluator's own `wsb_eval.validate_generation(request, config, result)` →
  PASS for 10/10: request `abc is None`, `cot == "full"`,
  `cfg_scale == 1.0`; `config["generation"] ==` the frozen `GENERATION`
  constant dict (programmatic equality); `overrides == {}`,
  `quantization "none"`, `model_dtype "bfloat16"`, `vae_dtype "float32"`;
  `backend "torch"` ∈ {torch, vllm}; `runtime_sha256` 64-hex
  (`8bf0def549c09fbf9620691ce20e8aafc3b1e40186c826df371bcfbb276cf2ab`,
  identical across all 10); `vae_decode "halo_crop"` with 1024/16; weights
  mot/vae sha256 + config sha256 equal the frozen
  GENERATOR/VAE(+config) constants in `wsb_eval.py`.
- `request.json` seed/cot/cfg_scale match the official row
  (`seed == [831001, 831019][j] + i`) for all 10.
- Independent recompute: `identity({request, config, weights})` reproduces
  each `result.json["identity"]` exactly (10/10).

### 4. Truncated candidates retained, not filtered — PASS

- Manifest: `wsb_002_r0_s831003` and `wsb_076_r1_s831095` have
  `"truncated": true` (only these two).
- Their `result.json` both record `"truncated": true` (e.g. 002_r0:
  abc phase hit the 4096 cap, `output_tokens: 4096`, `truncated: true`).
- Not filtered anywhere: both are present in `evaluation_inputs.jsonl`,
  in `scores/audio_manifest.jsonl` (all 10 staged for scoring), and in the
  8-job `scores/per.jobs.json` of the (later aborted) full-pilot scoring
  attempt. `verify_wsb_artifacts.py` treats truncated as allowed-recorded
  (`if r.get("truncated"): pass`), and `runs/wsb_pilot/audit.json` +
  `evidence/pilot_validation.json` record `truncated_but_complete: 2`,
  verdict FULL, problems [].

### 5. Prompt fidelity vs official manifest — PASS

For **all 10** candidates (superset of the requested "couple"),
`json.loads(request.json)["style"|"lyrics"]` are byte-equal after JSON
parsing to both:

- `/home/amd/Desktop/YuE2/benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl`
  rows 0, 1, 2, 76, 77 (`style`, `lyrics`), and
- the evaluator's frozen `wsb_metrics/data/evaluation_targets.jsonl`
  (`style`, `lyrics`) — the exact comparison `wsb_eval.prepare_inputs`
  performs (`Generated request differs from frozen WSB input`).

No prompt-text edits anywhere. `audit.json` unique_prompt_coverage 5.

### 6. Scoring summary vs validation evidence — PASS on values; coverage caveat = P1

`/home/amd/Desktop/YuE2/runs/wsb_pilot/scores/summary.json`:
`complete: true`, `errors: []`, mode `shard`, metrics per+songbench,
`full_192_standard_candidate_coverage: false`. Recorded values match
`evidence/pilot_validation.json` exactly (float-for-float):
PER micro/macro `0.19479495268138802`; SongBench Global Avg
`6.776798861367362`; Musicality `5.994098424911499`; Melody 6.7419…,
Arrangement 7.1213…, Vocal 7.1986…, Instrumental 7.0473…, Mixing 6.8677…,
Structure 6.4668…. Receipts (`scores/receipts/wsb_000_r{0,1}_*/per.json`,
`songbench.json`) exist and both worker logs show `complete` for both
candidates.

**Caveat (P1):** `summary.json` records `candidate_count: 2, prompt_count: 1`
— only the two prompt-0 candidates were actually scored. The 10-candidate
re-score started 22:19 (`per.jobs.json` with 8 jobs, new `protocol.json`,
`audio_manifest.jsonl`) and was aborted mid-PER (~00:12 per.log mtime, no
new receipts). `pilot_validation.json` discloses this accurately
(`note_8candidate_rescore`, "the 2-candidate shard run above is the
pilot-evaluator evidence"). The committed report
`reports/PHASE5_WSB_PILOT.md` §3 nevertheless states "`per,songbench` scored
10/10 with zero errors" — not supported by the artifacts (see Issues).

### 7. Evaluator patches 0006/0007 and release integrity — PASS

Fresh extraction of
`/home/amd/Desktop/YuE2/benchmark/WildSongBench/evaluation/wsb_metrics.tar.gz`
(`wsb_eval.py`, `release.json`, `src/mot_infer/eval_worker.py`) into
`/tmp/wsb_verify`:

- `diff` fresh-vs-live `wsb_metrics/wsb_eval.py`: exactly one hunk, byte-equal
  in content to hunk 1 of
  `/home/amd/Desktop/YuE2/evidence/YuE2-SGLang-ROCm/patches/0006-0007-wsb-evaluator-rocm.patch`
  (env-gated `WSB_ROCM_TORCH_OVERRIDE` torch-family exemption inside
  `verify_environment`; receipt gains `rocm_torch_override` + raw `errors`).
- `diff` fresh-vs-live `src/mot_infer/eval_worker.py`: exactly one hunk,
  byte-equal to hunk 2 of the patch (PER ASR via qwen_asr transformers
  backend under the same env gate; vLLM path preserved verbatim in the
  `else` branch).
- No other behavioral edits: all other live files compared via release
  digests (below); `artifact_storage.py` digest equals the original release
  hash.
- `release.json`: same 104-entry key set as the shipped release; exactly two
  entries differ fresh→live (`wsb_eval.py`, `src/mot_infer/eval_worker.py`);
  recomputed sha256 of both live modified files equals the live release.json
  values (`6a4a53ed…`, `569404c7…`). So the modified files are covered by
  the integrity manifest, and everything else is unchanged.
- Run-time binding: `scores/protocol.json` (22:19) carries the live
  (patched) code hashes; `scores/per.environment.json` and
  `songbench.environment.json` both record `passed: true`, python 3.12.11,
  `rocm_torch_override: [torch, torchaudio, torchvision, triton]` with the
  actual substituted versions and the raw lock errors — the override is
  explicit, scoped to the torch family only, as the report claims.

### 8. Driver safety review (`scripts/run_wsb.py`) — PASS

- **Never alters style/lyrics/seeds/budgets:** payload is
  `{"style": row["style"], "lyrics": row["lyrics"], "seed": seed, ...,
  **OFFICIAL}`; seeds come from `row["candidate_ar_seeds"][:candidates]`;
  `OFFICIAL` is a frozen constant (cot full, ode 32, 9000/4096, 1024f+16h).
  No string rewriting of prompts anywhere in the file.
- **Per-candidate WAV names:** `wav_name = f"{ident}.wav"`; confirmed on disk
  (10 distinct `songs/wsb_*.wav`). Git history shows this was hardened from
  a shared `audio.wav` name before the pilot's stage-2 run (commit
  ccb5520), with the response check tightened to the exact file.
- **Resume:** `candidate_complete()` calls the official `verify_result` and
  skips only candidates that verify complete (appends a
  `complete(resumed)` marker). Matches observed manifest lines 3-4.
- **rmtree:** `shutil.rmtree(cand)` executes only when `candidate_complete`
  returned False (the complete case `continue`s above it), i.e. only
  stale/partial dirs are removed, never verified-complete ones.
- `cfg_scale` is deliberately not sent (documented in-code; server PR head
  rejects the key); the effective single-branch CFG 1.0 is materialized into
  `request.json` by `finalize_candidate.py`, and the evaluator's
  `validate_generation` (which requires `cfg_scale == 1.0`) passes on all
  10 bundles (P3-3 notes the residual trust assumption).
- Evidence copies of the three scripts in
  `evidence/YuE2-SGLang-ROCm/scripts/` are byte-identical to
  `/home/amd/Desktop/YuE2/scripts/` (diff -q, all three).

## Issues

- **P1-1 (report accuracy, correction required):**
  `reports/PHASE5_WSB_PILOT.md` §3 states "`per,songbench` scored 10/10 with
  zero errors; per-candidate receipts in runs/wsb_pilot/scores/". Artifacts
  show only 2/10 candidates scored (prompt 0): `scores/summary.json`
  `candidate_count: 2, prompt_count: 1`; receipts exist for exactly
  `wsb_000_r0_s831001` and `wsb_000_r1_s831019`; the 8-candidate re-score
  (`per.jobs.json` 8 jobs, started 22:19) was aborted mid-PER with no new
  receipts. The claim was committed at 00:33 (505600f), after the abort
  (~00:12). `evidence/pilot_validation.json` describes the true scope
  correctly, and every number quoted in the report's observation section is
  the honest 2-candidate value, so this is a wrong coverage statement, not
  fabricated data. Fix: reword the bullet to "2/10 pilot candidates scored
  (prompt 0); the 8-candidate re-score was aborted to protect the 384-run
  critical path; full scoring in Phase 7".
- **P2-1 (stale manifest identities for the 2 stage-1 candidates):** in
  `generation_manifest.jsonl`, `identity` for `wsb_000_r0_s831001`
  (`5026c66a…`) and `wsb_000_r1_s831019` (`bf71fc24…`) no longer equals the
  current `result.json` identities (`570c5ce9…` / `cc34b973…`); the other 8
  match. Root cause fully reproduced by this reviewer: the stage-1
  candidates were finalized with the pre-ccb5520 `finalize_candidate.py`
  (config = bare `GenerationConfig.to_dict()`, request `cfg_scale: null`),
  then re-finalized at 20:15 with the upgraded contract (cfg materialized +
  full config wrapper + runtime hash), which rewrote
  request/config/result.json and changed the identity; the append-only
  manifest kept the old values. I recomputed
  `identity({request(cfg=null), config=bare-generation, weights})` and got
  exactly `5026c66a…`, confirming the explanation. Current artifacts are
  self-consistent (verify_result + identity recompute pass) and the
  evaluator never reads the run manifest, but the manifest misstates the
  current identity for 2/10 records and no manifest line records the new
  ones. Fix: append a correction note or re-record identities for those two
  ids in a follow-up evidence file.
- **P3-1:** manifest contains the two extra `complete(resumed)` marker lines
  (duplicate ids, no detail fields) — intentional resume semantics, but
  consumers keying on id should take the last full record.
- **P3-2:** `request.json["id"]` holds the wav filename
  (`wsb_000_r0_s831001.wav`) rather than the official driver's bare ident;
  the evaluator ignores `id`, no contract violated.
- **P3-3:** `cfg_scale=1.0` in the bundles is materialized post-hoc by the
  finalizer rather than carried from an explicit server parameter; the
  in-code justification (SongRequest guidance resolving None+full → 1.0)
  plus `timing.*.cfg_branches == 1` in every result.json corroborate
  single-branch decoding, but the link is documentary, not enforced by the
  server payload.
- **P3-4:** `scores/` mixes the completed 2-candidate run (summary.json,
  per_song.jsonl, receipts, songbench jobs — 20:30) with the aborted
  10-candidate attempt (per.jobs.json, protocol.json, audio_manifest —
  22:19). `summary.json` remains the 2-candidate run's, which is correct
  but easy to misread.

## Evidence paths (primary)

- `/home/amd/Desktop/YuE2/runs/wsb_pilot/generation_manifest.jsonl`,
  `evaluation_inputs.jsonl`, `generation_summary.json`, `audit.json`,
  `songs/wsb_*/` (request/config/result/plan/flac), `scores/summary.json`,
  `scores/per_song.jsonl`, `scores/receipts/`, `scores/per.jobs.json`,
  `scores/protocol.json`, `scores/{per,songbench}.environment.json`,
  `scores/{per,songbench}.log`
- `/home/amd/Desktop/YuE2/evidence/YuE2-SGLang-ROCm/evidence/pilot_manifest.jsonl`,
  `pilot_validation.json`
- `/home/amd/Desktop/YuE2/evidence/YuE2-SGLang-ROCm/patches/0006-0007-wsb-evaluator-rocm.patch`,
  `patches/README.md`
- `/home/amd/Desktop/YuE2/scripts/run_wsb.py`, `finalize_candidate.py`,
  `verify_wsb_artifacts.py`
- `/home/amd/Desktop/YuE2/benchmark/WildSongBench/code/generate.py`,
  `benchmark/reproduction_manifest.jsonl`, `wsb_metrics/wsb_eval.py`,
  `wsb_metrics/artifact_storage.py`, `wsb_metrics/release.json`,
  `wsb_metrics/src/mot_infer/eval_worker.py`,
  `evaluation/wsb_metrics.tar.gz`
- Reviewer scratch (fresh extraction): `/tmp/wsb_verify/`
