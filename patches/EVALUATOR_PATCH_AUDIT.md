# Evaluator Patch Audit — 0006 / 0007 (frozen WildSongBench evaluator on ROCm)

**Audit date: 2026-10-12. Scope: exact deviation from the official evaluator,
parity risk analysis, and the controlled same-audio evidence that governs what
we may claim. Scoring formulas, candidate selection, aggregation and every
metric model are untouched.**

## 1. Exact differences from the pristine evaluator

Reference: `evaluation/wsb_metrics.tar.gz` from WildSongBench @ `e361b85a`
(extracted fresh to `/tmp` and diffed tree-wide). **Exactly three files
differ**; every other code file is byte-identical (the evaluator's own
`verify_release()` confirms the remaining hashes):

| File | Change | Purpose |
|---|---|---|
| `wsb_eval.py` | one function: `verify_environment` (+12 lines, −0) | env-gated torch-family exemption (0006) |
| `src/mot_infer/eval_worker.py` | one method: `PerScorer.__init__` (+31/−0, original branch preserved) | PER ASR via qwen_asr transformers backend under the same env gate (0007) |
| `release.json` | 2 hash entries + 1 disclosure note | keeps `verify_release()` covering the patched files |

Environment substitutions inside the evaluator's pinned venvs (recorded in
every `<metric>.environment.json` receipt with a `rocm_torch_override`
marker; all other 224 lock entries match exactly, Python 3.12.11 unchanged):

| venv | package | pinned (CUDA) | actual (ROCm) |
|---|---|---|---|
| metrics | torch | 2.9.1 | 2.10.0+rocm7.14.1 |
| metrics | torchaudio | 2.9.1 | 2.10.0+rocm7.14.1 |
| metrics | torchvision | 0.24.1 | 0.25.0+rocm7.14.1 |
| metrics | triton | 3.5.1 | 3.6.0+rocm7.14.1 |
| eval | torch | 2.7.0 | 2.10.0+rocm7.14.1 |
| eval | torchaudio | 2.7.0 | 2.10.0+rocm7.14.1 |
| eval | torchvision | 0.22.0 | 0.25.0+rocm7.14.1 |

### What patch 0006 does NOT touch
Metric computation, `prepare_inputs` (incl. request/config validation and
MP3 encoding receipts), `phoneme_result`, PER selection keys, SongBench/MuLan/
AllMusicCaps workers, `summarize`, Q3O code. Only the *admission control*
gains an explicit, receipt-recorded exemption for the four torch-family
packages, active only under `WSB_ROCM_TORCH_OVERRIDE=1`.

### What patch 0007 does NOT touch
`PerScorer.score_batch` (chunk counting, repeat loop, phoneme scoring),
`phoneme_result`, selection. Only the ASR *engine construction* and the
per-chunk raw-output recorder differ, under the same env gate; the vLLM
branch is preserved verbatim for CUDA hosts.

## 2. Transformers-vs-vLLM PER parity analysis

What is **identical by construction** (shared `qwen_asr` code):
chunking (`split_audio_into_chunks`, 30 s), prompt construction, processor,
decode/postprocess (`parse_asr_output`), language detection, 4-repeat loop,
phonemization, edit distance, selection keys.

What **differs**:

1. **Inference engine.** vLLM 0.14.0 (paged attention, continuous batching,
   its CUDA kernels) vs HF transformers `generate` (eager attention path on
   ROCm). Both decode greedily (vLLM `temperature=0.0`; HF `generate` without
   sampling args is argmax). Bit-identical logits are NOT expected across
   engines; near-tied tokens can flip, changing transcripts at the margin.
2. **Batch composition sensitivity (measured, see §3).** HF batching pads to
   the longest sequence in the batch; which chunks share a batch depends on
   the candidate set being scored. vLLM's continuous batching has its own
   composition dynamics. → PER is **not a backend-invariant scalar** at the
   single-candidate level.
3. **EOS/cap semantics.** Mapped faithfully: HF continuation length ≥ cap ⇒
   `finish_reason='length'`, else `'stop'` (the receipt keeps generated token
   counts either way).
4. **Observed failure mode.** One pilot candidate (wsb_076_r1, English)
   received an empty transcription — Qwen3-ASR emitted only
   `language None<asr_text>` and stopped (4/4 repeats, `asr_all_terminated`
   true), yielding PER 1.0 on 505 reference phonemes. Audio integrity was
   verified independently (generation checks + FLAC binding), so this is an
   ASR-side behavior, retained unfiltered per protocol and **counted and
   disclosed** in every PER aggregate we publish. Whether the CUDA/vLLM
   reference exhibits this mode is unknown from this host.

## 3. Controlled same-audio comparison (evidence, not a claim)

- **Run A** (2026-10-11): 2 pilot candidates scored → micro-PER 0.19479.
- **Run B** (2026-10-12): the same 2 candidates inside a 10-candidate set →
  one candidate identical to Run A (bit-equal PER/edits), one drifted
  (0.17350/110 edits → 0.16719/106 edits). **Different batch composition,
  same audio ⇒ different transcript.**
- **Run C** (2026-10-12): the identical 10-candidate set scored again,
  independent process, ~1 h later → **10/10 candidates bit-identical to Run B**
  (PER and edits). Within-set determinism: **IDENTICAL**.

## 4. Claims permitted by this evidence

- **NOT claimed:** ROCm/transformers PER ≡ CUDA/vLLM PER. A cross-backend
  equivalence claim would require the controlled same-audio comparison on a
  CUDA host (protocol: score ≥10 identical candidates under both backends,
  publish per-candidate PER deltas and transcript diffs; neither host is
  available here). Until then every published PER is labeled
  **"ASR backend: qwen_asr/transformers on ROCm"**.
- **Claimed:** the frozen scoring formulas, selection and aggregation are
  unmodified (3-file diff, hash-covered); our pipeline is (per Run C) exactly
  reproducible for a fixed candidate set; deviations concentrate in the ASR
  engine substitution and are disclosed per-candidate via receipts.
- Phase 8 comparisons vs the H800 reference will present PER alongside the
  empty-transcript count and this audit, without asserting evaluator
  equivalence.

## 5. Reproduction

```
# exact diff vs pristine
tar xzf evaluation/wsb_metrics.tar.gz -C /tmp/pristine_wsb
diff -r /tmp/pristine_wsb/wsb_metrics wsb_metrics            # 3 files
# same-audio determinism (any fixed candidate set)
WSB_ROCM_TORCH_OVERRIDE=1 python wsb_metrics/wsb_eval.py score \
  --input <inputs>.jsonl --output /tmp/runB --mode shard --metrics per   # x2, diff
```
