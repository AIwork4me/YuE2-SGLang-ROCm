# RC5.1 P0.5 — Official PER Full Scoring & Selection Statistics

## Protocol (frozen)

- ASR: `Qwen/Qwen3-ASR-1.7B`, asr_repeats=4 (1536 receipts for 384 candidates),
  batch_size=8, max_new_tokens=4096, temperature=0.0, seed=0, language=auto.
- Engine: qwen_asr **transformers** backend on ROCm (`WSB_ROCM_TORCH_OVERRIDE=1`,
  disclosed substitution — the official engine is vLLM 0.14.0 on CUDA).
- Scoring: official `PERScorer.phoneme_result` + `historical_per.edit_distance`
  on the frozen, hash-gated evaluator tree.
- Run: `wsb_eval score --mode standard --metrics per` on all 384 new RC5.1
  candidates; evaluator rc=0, 384/384 complete, 0 failures.

## Results

| Set | micro PER | macro PER | edits / phonemes |
|---|---|---|---|
| **selected-192 (official best-of-2)** | **17.7699%** | 16.5407% | 27 563 / 155 111 |
| selected zh (94) | 17.6930% | — | |
| selected en (98) | 17.8376% | — | |
| unselected-192 only | 30.8147% | 28.8405% | |
| all 384 (evaluator "unselected" naming) | 24.2923% | 22.6906% | 75 360 / 310 222 |

95% bootstrap CI (prompt-level, 10 000 draws): **[15.22%, 20.56%]**.

Error decomposition (selected-192, S+D+I verified equal to official edits for
every candidate): S=14 552, D=10 589, I=2 422 — deletions dominate, driven by
capped/empty ASR outputs that lose whole lyric lines.

## Failure taxonomy (384 candidates)

- 10 candidates: empty transcript in **all four** repeats (confirmed-empty;
  4 of these were the historically reproducible English empties — see P1.1)
- 112 candidates: token cap reached in at least one repeat (224 capped repeats
  across selected-192)
- 11 candidates: PER = 1.0 (each labelled: empty vs capped vs genuine — never
  conflated; 10 empty-set members + capped/genuine remainder)

## Independent selection audit

Full official ordering key `(per, edits, |len(phonemes)−reference|,
candidate_index)` recomputed independently of the evaluator's
`select_candidates`:

- raw coverage 384/384; prompt coverage 192/192
- evaluator vs independent candidate identity: **192/192**
- selected audio-hash match: **192/192**; zero inversions, zero tie-break errors
  (the historical prompt-19 simplified-key bug does not recur)

Frozen manifest: `05_SELECTED_MANIFEST.json` (immutable; binds per-candidate
selected audio sha256 + candidate FLAC sha256). All later metrics use exactly
this selection.

## Reference comparison

| Reference | PER |
|---|---|
| Paper | 8.44% |
| Author SGLang (CUDA) | 8.1471% |
| Historical W7900 Arm B (same substitution) | 17.7628% |
| **RC5.1 W7900 (this run)** | **17.7699%** |

Delta vs historical: +0.007 pp — the W7900 PER observation **reproduces
essentially exactly** under the frozen ROCm transformers substitution.
The ~9.3 pp gap to the official reference is the subject of the P1.1
same-audio causal study (engine/backend numerics vs model behaviour), not of
any scoring shortcut: transcripts, repeats, caps and failures were all kept
as produced.
