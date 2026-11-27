# CUDA_Q3O_RUNBOOK.md — RC6 B4: same-audio official-CUDA Q3O experiment

**Status: comparator READY and self-tested; CUDA execution BLOCKED_EXTERNAL
(no CUDA host). This runbook is the exact procedure for the author/Owner
side. Pre-register the criteria BEFORE running — never after seeing
results.**

## 1. Freeze the comparison set (both sides identical)

```bash
# Side A (already done, frozen): RC5.1 ROCm-adapted receipts
#   /data/yue2-runs/rc5-q3o/rc5_1-full-192  (identity.json + receipts/ + summary.json)

# Side B (CUDA host): verify the SAME audio bytes first
python3 scripts/rc6_audio_manifest.py --from-songbench-sel <run_dir> --out cuda_audio_manifest.jsonl
sha256sum cuda_audio_manifest.jsonl   # must equal the ROCm side's manifest sha
```

Join key = `generation_id`; audio identity = per-file SHA256 (MP3 encodings
must be byte-identical to the frozen evaluation set — re-encoding the same
FLAC is NOT the same input).

## 2. Run the official CUDA judge

Use the evaluator bundle's official Q3O path (vLLM 0.14.0, FlashAttention
2.8.3, official prompt/parser/weights — exactly the README's Q3O section),
on the frozen 192 selected candidates (or the pre-frozen diagnostic subset:
`07_DIAGNOSTIC_SUBSET.json`, normal/hard/short/long/zh/en, chosen BEFORE any
result). Emit receipts in the `rc5_q3o_judge.py` schema:

```
receipts/<generation_id>/q3o.json  {status, scores.q3o, q3o.{generation_id,
  judge_model, overall_0_5, weight_sum, dimensions.<dim>.{score,weight},
  raw_judgement, timing.*}} + identity.json + summary.json
```

(a small collector mirroring our receipt fields is enough; the comparator
only needs the fields above).

## 3. Pre-register equivalence criteria (protocol owner / author — BEFORE the run)

`criteria.json`:

```json
{"criteria": [
  {"kind": "mean_delta_within", "max_abs": 0.10,
   "note": "mean paired overall delta <= 0.10 (example value — owner MUST fix)"},
  {"kind": "agreement_at_least", "ladder": "within_1_0", "min_count": 180,
   "note": ">=180/192 candidates within 1.0 (example — owner MUST fix)"}
]}
```

## 4. Compare

```bash
python3 scripts/rc6_q3o_comparator.py \
  --rocm-dir /data/yue2-runs/rc5-q3o/rc5_1-full-192 \
  --cuda-dir <cuda run dir> \
  --selected-manifest reports/w7900_rc5/rc5_1/05_SELECTED_MANIFEST.json \
  --criteria criteria.json \
  --out reports/developer_reference/author/Q3O_CUDA_COMPARISON.json
```

Output: coverage (join + one-sided lists), judge identities, means,
agreement ladder (exact / ±0.5 / ±1.0 / >1.0), per-stratum means (language,
duration terciles), 10k-draw paired bootstrap CI on the mean delta,
per-candidate paired rows (overall + every dimension), failure taxonomy,
tie-break disclosure, and the verdict under the pre-registered criteria
(else `PENDING_CRITERIA`).

## 5. Rules

- Pilot-subset equivalence NEVER scales to full equivalence — report both
  separately.
- The comparator never decides equivalence by itself; it applies only the
  criteria file.
- Any audio-hash mismatch on the CUDA side = the run is invalid (rerun with
  the exact frozen bytes).
- Self-test (already green, re-run anytime):
  `python3 scripts/rc6_q3o_comparator.py --selftest --rocm-dir <roc run> --out st.json`
