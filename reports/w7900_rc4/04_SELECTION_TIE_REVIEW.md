# RC4 M4.2 — Prompt-19 Selection Tie Review

Date: 2026-11-22. Evidence: frozen Arm B run `armB_full_20261119T015756Z`
(`scores/per_song.jsonl`, `scores/summary.json`; hashes in
`/data/yue2-runs/rc4_evidence/frozen_scores_manifest_20261122.txt`).

## RC3 observation

192 prompts, 191 byte-identical selections between the official evaluator and
an independent recomputation; prompt 19 diverged (official r1, independent r0)
and was classified as a "PER-equal tie" with unclear tie-break semantics.

## RC4 finding: the tie is fully specified — no under-specification exists

The official frozen implementation (`wsb_eval.py::select_candidates`, final
patched hash `efb89042…`) minimizes this exact 4-tuple per prompt:

```
(per, edits, |len(asr_repeats[selected_asr_repeat].phonemes) - reference_phonemes|, candidate_index)
```

Prompt 19 numeric facts (public-safe counts/rates only):

| candidate | seed    | per              | edits | ref phonemes | selected-repeat phonemes | delta |
|-----------|---------|------------------|-------|--------------|--------------------------|-------|
| r0        | 831020  | 0.2260127931769723 | 106 | 469          | 458                      | 11    |
| r1        | 831038  | 0.2260127931769723 | 106 | 469          | 472                      | 3     |

The first two components tie bit-exactly; the **third** component decides:
3 < 11 → **r1 legitimately wins**. `candidate_index` is only reached on a full
4-component equality. Python tuple comparison is deterministic; no sort
stability is ever consulted (min over a key, not a stable sort of equal keys).

## Why the independent recomputation chose differently (defect, now fixed)

Two independent-analysis scripts carried unfaithful selection keys:

1. `scripts/per_cross_arm_analysis.py::sel_key`
   - phoneme term summed over **all** `asr_repeats` instead of the selected
     repeat;
   - final component `selected_asr_repeat` instead of `candidate_index`.
2. `scripts/rc2_per_length_analysis.py` diagnostic fallback
   - third component `abs(reference_phonemes - per)` — a phoneme **count**
     minus the PER **rate** (dimensionally meaningless);
   - final component `selected_asr_repeat` instead of `candidate_index`.

With the old `sel_key`, the divergence reproduces **exactly** at prompt 19 and
nowhere else (verified against the frozen receipt), confirming the causal
attribution.

## Verification

- Exact official key recomputed from frozen `per_song.jsonl`: **192/192
  selection identities match** `summary.json::selected_candidates`
  (prompt_index, candidate_index, seed).
- Aggregate impact: none — the official selection and therefore all
  selected-192 aggregates were already correct; no historical number changes.

## Fixes (this branch)

- `scripts/per_cross_arm_analysis.py::sel_key` rewritten to the exact official
  4-tuple (with provenance comment).
- `scripts/rc2_per_length_analysis.py` fallback rewritten to the same key.
- New `tests/test_selection_tie_semantics.py` (5 tests):
  - prompt-19 scenario selects r1 under the official key;
  - the pre-RC4 unfaithful key reproduces the r0 divergence (mutation
    control);
  - 500 randomized rows: `sel_key` ≡ official key component-for-component;
  - full-equality tie falls to `candidate_index`;
  - frozen-receipt 192/192 identity check (skipped when evidence tree absent).

Result: 5/5 PASS (`pytest tests/test_selection_tie_semantics.py`).

## Classification

- Official frozen implementation: **CORRECT, deterministic, fully specified**.
- RC3's "tie ambiguity" classification: superseded — no ambiguity exists.
- Independent verification logic: **defect found and fixed** with regression
  coverage.
- No frozen result, score, or selection was modified.
