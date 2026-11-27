# 02_ASR_RESUME_RCA.md — RC6 A2.2: root-cause of the historical resume path

## Defect (RC5.1 state)

`scripts/rc5_asr_vllm_native.py` (pre-RC6) skipped already-done candidates by
**candidate id alone**:

```python
done = set()
if a.out.is_file():
    for line in a.out.read_text().splitlines():
        try:
            done.add(json.loads(line)["id"])
        except ValueError:
            pass
```

Consequences (failure modes, all now closed):

1. **Audio substitution undetected** — if the audio file behind a manifest id
   changed (regenerated, wrong run, corruption), the old transcript was
   silently reused; scoring would then compare a transcript of audio A
   against reference lyrics for audio B.
2. **Model substitution undetected** — reruns with a different ASR snapshot
   or weights reused old transcripts (no model hashes anywhere).
3. **Engine/config substitution undetected** — vLLM/torch/dtype/repeats
   changes reused old transcripts.
4. **Missing repeats silently accepted** — a row with 1 of 4 repeats was
   treated as done (scorer would then score 1 repeat).
5. **Duplicate candidate ids** possible (append-mode file, no check) →
   double-counted candidates, wrong denominators.
6. **Invalid JSONL tail** (torn write on crash) was skipped line-by-line with
   a bare `except ValueError: pass` — a truncated final line vanished
   silently; a mid-file corruption could orphan everything after it.
7. **No receipt self-hash** — nothing prevented post-hoc edits to a
   transcript file.
8. **Scorer** `rc5_score_transcripts.py` used a bare `assert` for the audio
   check (disabled under `python -O`), had no duplicate/coverage/repeat/
   engine-mixing checks, and a missing candidate was silently ignored
   (micro PER computed over whatever was present — a wrong denominator).

## Actual risk in RC5.1 (what the audit found)

The read-only audit of the **historical** files found: 384/384 audio SHA
match vs manifest, 0 duplicates, uniform 4 repeats, single engine env per
arm, valid tails. **None of the failure modes materialized in the frozen
evidence** — but nothing in the tooling would have caught them if they had.
The corrected-arm numbers (8.4488%) therefore stand as scored; the RC6
hardening protects all FUTURE runs (and would catch a corrupted resume
today: exit codes 3/4 instead of silent reuse).

## Fix (minimal, fail-closed)

- `scripts/rc6_asr_identity.py` — the identity contract + audit + quarantine
  (see `02_ASR_IDENTITY_CONTRACT.md`).
- `scripts/rc5_asr_vllm_native.py` — computes the full run identity before
  GPU work, embeds it + `transcript_receipt_sha256` in every receipt, audits
  an existing output file, quarantines torn tails, refuses (exit 3/4) on
  duplicates/rejections, re-runs only reusable-clean + missing + incomplete.
- `scripts/rc5_score_transcripts.py` — explicit `ScorerValidationError`s
  (never `assert`), duplicates/coverage/repeat/engine checks, scoring
  identity binding, supersede-not-overwrite for outputs, denominator +
  aggregation audits.

## Verification

- 20/20 negative controls PASS (`tests/test_rc6_asr_identity.py`,
  `02_ASR_NEGATIVE_CONTROLS.json`): every claimed failure mode is
  demonstrably detected.
- GREEN regression: re-scoring a frozen E2 slice reproduces the frozen
  per-row numbers exactly (official math untouched).
- Read-only provenance audit of both historical arms: 0 violations
  (`02_EVALUATOR_PROVENANCE_VERDICT.json`).
