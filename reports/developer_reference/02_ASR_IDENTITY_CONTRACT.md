# 02_ASR_IDENTITY_CONTRACT.md — RC6 A2: ASR_RUN_IDENTITY contract

## Contract

Every ASR evaluation run (new, RC6 onward) carries `ASR_RUN_IDENTITY`
(`scripts/rc6_asr_identity.py`, schema `yue2-rc6-asr-run-identity/1`), a
hash-bound record of **everything that can change a transcript**:

| Field | Bound content |
|---|---|
| `model` | ASR repository root, snapshot revision, **per-file SHA256** of every model/processor file, aggregate `files_sha256` |
| `engine` | implementation class, framework versions (vLLM / torch / HIP), device name, platform registration, dtype, seed |
| `audio_preprocessing` | audio loading + chunking function identity + **source-file SHA256 of `qwen_asr.inference.utils`**, sample rate |
| `decoding` | temperature / top_p / top_k / max_tokens / seed / **repeats** / batch policy / gpu_memory_utilization |
| `scoring` | scorer-step reference + **audio manifest SHA256** (scoring identity is SEPARATE — see below) |
| `driver` | the runner script path + **its own source SHA256** |
| `run_identity_sha256` | canonical SHA256 over all of the above |

## Receipt-level binding

Every per-candidate receipt embeds: `candidate_id`, `prompt_index`,
`candidate_index`, `audio_sha256`, `run_identity` (full contract),
`run_identity_sha256`, `transcript_receipt_sha256` (content hash of the
receipt itself), `repeat_count`, `status`.

## Fail-closed resume (replaces candidate-id-only skipping)

`scripts/rc5_asr_vllm_native.py` (RC6-hardened) audits an existing output
file BEFORE any GPU work and refuses to continue unless the audit is clean:

| Audit outcome | Action |
|---|---|
| Exact identity + audio + repeat match | REUSE (skip) |
| Audio SHA mismatch vs manifest | **REJECT** → exit 4, "start a new --out path" |
| Model file-hash mismatch | **REJECT** → exit 4 |
| Engine version/impl mismatch | **REJECT** → exit 4 |
| Decoding/config mismatch | **REJECT** → exit 4 |
| Fewer repeats than requested | INCOMPLETE → re-run that candidate |
| Duplicate candidate IDs | **FAIL** → exit 3 |
| Invalid JSONL tail | **QUARANTINE** the original (timestamped copy, supersede-not-overwrite), keep the valid prefix, bounded repair, re-audit |
| Manifest row missing | **FAIL** |

The audit receipt (`*.resume_audit.json`) is written next to the output file.

## Scoring identity (separate arm identity)

`scripts/rc5_score_transcripts.py` (RC6-hardened) records a
`scoring_identity` (SHA256 of `historical_per.py`, `eval_worker.py`, the
audio manifest) in **every output row and summary**. Writing a different
scoring identity into an existing output file is refused (supersede, never
overwrite). Scorer validation is fail-closed (no bare `assert`):

- duplicate candidate ids → fail
- transcript id unknown to manifest (cross-arm mixing) → fail
- audio SHA mismatch → fail
- wrong / inconsistent repeat counts → fail
- missing manifest candidates → fail (no silent skip; `--allow-partial` is
  diagnostic-only and recorded in the summary)
- mixed engine identities inside one transcripts file → fail
- per-row `per ≠ edits/reference_phonemes` → fail (denominator audit)
- micro PER re-derived from raw sums and cross-checked (aggregation audit)

The official PER math (`mot_infer.eval_worker.phoneme_result` selection +
edit distance) is **byte-identical** to the RC5.1 path; the GREEN regression
re-scored a frozen E2 slice and reproduced the frozen numbers exactly.

## Historical arms (RC5.1) — read-only audit

Both frozen arms were audited read-only
(`scripts/rc6_evaluator_provenance.py` → `02_EVALUATOR_PROVENANCE_VERDICT.json`):

- **T (transformers)**: 384/384 rows, audio SHA vs manifest 384/384, 0
  duplicates, uniform 4 repeats, engine env consistent.
- **V (vLLM E2)**: 384/384 transcripts + 384/384 scored rows, audio SHA vs
  manifest 384/384 (both levels), 0 duplicates, uniform 4 repeats, single
  engine env, transcripts↔rows 1:1.
- Model file hashes were **not recorded at run time** by the RC5.1 runners;
  RC6 recomputes them from the unchanged snapshots (disclosed as
  `RECOMPUTED_NOW_CONSISTENT`) and embeds them for all future runs.
- No re-run was needed; no frozen receipt was modified.

## Machine-readable evidence

- `02_ASR_RESUME_RCA.md` — root-cause analysis of the old resume path.
- `02_ASR_NEGATIVE_CONTROLS.json` — 20/20 controls PASS (each failure mode
  demonstrably detected) + the GREEN regression.
- `02_EVALUATOR_PROVENANCE_VERDICT.json` — both-arm provenance verdict.
