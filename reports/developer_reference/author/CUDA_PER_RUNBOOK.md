# CUDA_PER_RUNBOOK.md — RC6 B3: same-audio official-CUDA PER experiment

**Status: prepared + tested comparator; execution BLOCKED_EXTERNAL (no CUDA
host). Executed by: the author or any authorized holder of a CUDA host with
vLLM 0.14.0. Pre-register the equivalence criteria BEFORE running.**

## 0. Pre-registered criteria (to be fixed by the protocol owner/author)

Example (the owner MUST fix the actual values before any run):

```json
{"criteria": [
  {"kind": "per_micro_delta_within", "max_abs_pp": 0.5,
   "note": "|selected micro PER(CUDA) - 8.4488%| <= 0.5 pp"},
  {"kind": "empty_delta_within", "max_count": 3,
   "note": "empty-transcript count within 3 of the vLLM ROCm arm's"}
]}
```

## 1. Restore the exact audio (identity first)

```bash
# handoff package (owner-transferred checkpoints; hash-bound):
ls /data/yue2-runs/rc5-per-experiments/rc5_1_cuda_handoff/
#   HANDOFF_MANIFEST.json — run identity + all 384 candidate audio SHA256
#   README_CUDA_HANDOFF.md — the exact steps below
python scripts/rc5_cuda_handoff.py restore-check \
    --manifest HANDOFF_MANIFEST.json --backup-dir <transferred checkpoints>
```

Audio identity rule: per-file SHA256 must equal the manifest (same MP3
bytes). Same *song* ≠ same *file*: re-encoded MP3 is NOT the same input.

## 2. Run the official CUDA evaluator

Frozen for this experiment (from the RC5.1 receipts):

| Item | Value |
|---|---|
| ASR model | Qwen/Qwen3-ASR-1.7B (snapshot 7278e1e7; file hashes in the RC6 provenance audit) |
| Engine | vLLM **0.14.0** CUDA + qwen_asr 0.0.6 bundled model class |
| Prompt | the model's chat template on [system: context, user: [audio]] |
| Repeats | 4 · greedy (temperature 0, top_p 1, top_k off) · max_tokens 4096 |
| Scorer | frozen evaluator `historical_per` + `phoneme_result` (code hashes pinned) |
| Selection | official ordering key (per, edits, |Δphonemes|, candidate_index) |

The exact command is embedded in `HANDOFF_MANIFEST.json`
(`official_command_on_cuda`).

## 3. Compare against BOTH ROCm arms

```bash
python scripts/rc5_cuda_handoff.py compare \
    --rocm <frozen transformers per_song.jsonl> --cuda <cuda per_song.jsonl> \
    --out compare_T.json
python scripts/rc5_cuda_handoff.py compare \
    --rocm <corrected vLLM rows.jsonl> --cuda <cuda per_song.jsonl> \
    --out compare_V.json
```

Report: coverage, per-candidate PER, S/D/I, empty + cap counts, selection
changes vs both selections, paired bootstrap CIs, residual discrepancies —
plus the RC6 2×2 attribution update
(`03_PER_PAIRED_ATTRIBUTION.json` gains the official column).

## 4. Rules

- Same 384 audio files, hash-verified, before any inference.
- Criteria fixed before the run; the comparator never invents thresholds.
- Discrepancies are reported, never tuned away.
- The result updates G12 (official CUDA PER comparison) only when executed
  for real; until then it stays BLOCKED_EXTERNAL.
